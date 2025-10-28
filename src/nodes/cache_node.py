"""
Distributed Cache with MESI coherence protocol.
Supports cache coherence across multiple nodes with LRU replacement.
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional
from enum import Enum
from dataclasses import dataclass, field
from collections import OrderedDict

from src.nodes.base_node import BaseNode
from src.utils.config import Config
from src.communication.message_passing import Message, MessageType


logger = logging.getLogger(__name__)


class CacheState(Enum):
    """MESI cache line states."""
    MODIFIED = "M"
    EXCLUSIVE = "E"
    SHARED = "S"
    INVALID = "I"


@dataclass
class CacheEntry:
    """Entry in the cache."""
    key: str
    value: Any
    state: CacheState = CacheState.INVALID
    timestamp: float = field(default_factory=time.time)
    access_count: int = 0


class LRUCache:
    """LRU Cache implementation."""
    
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
    
    def get(self, key: str) -> Optional[CacheEntry]:
        """Get value from cache."""
        if key not in self.cache:
            return None
        
        self.cache.move_to_end(key)
        entry = self.cache[key]
        entry.access_count += 1
        entry.timestamp = time.time()
        
        return entry
    
    def put(self, key: str, value: Any, state: CacheState = CacheState.EXCLUSIVE):
        """Put value in cache."""
        if key in self.cache:
            entry = self.cache[key]
            entry.value = value
            entry.state = state
            entry.timestamp = time.time()
            entry.access_count += 1
            self.cache.move_to_end(key)
        else:
            if len(self.cache) >= self.capacity:
                evicted_key, evicted_entry = self.cache.popitem(last=False)
                logger.debug(f"Evicted key {evicted_key} from cache")
            
            self.cache[key] = CacheEntry(key=key, value=value, state=state)
    
    def invalidate(self, key: str):
        """Invalidate a cache entry."""
        if key in self.cache:
            self.cache[key].state = CacheState.INVALID
    
    def remove(self, key: str) -> Optional[CacheEntry]:
        """Remove entry from cache."""
        return self.cache.pop(key, None)
    
    def set_state(self, key: str, state: CacheState):
        """Set state of a cache entry."""
        if key in self.cache:
            self.cache[key].state = state
    
    def size(self) -> int:
        """Get current cache size."""
        return len(self.cache)
    
    def clear(self):
        """Clear the cache."""
        self.cache.clear()


class CacheNode(BaseNode):
    """
    Distributed Cache Node with MESI coherence protocol.
    
    Features:
    - MESI cache coherence protocol
    - LRU/LFU cache replacement
    - Distributed cache invalidation
    - Performance metrics
    - Cache miss handling
    """
    
    def __init__(self, config: Config):
        super().__init__(config)
        
        self.cache = LRUCache(capacity=config.cache_size)
        
        self.coherence_protocol = config.cache_coherence_protocol
        self.replacement_policy = config.cache_replacement_policy
        
        self.directory: Dict[str, Dict[str, CacheState]] = {}
        
        self.stats = {
            'hits': 0,
            'misses': 0,
            'invalidations': 0,
            'evictions': 0,
            'coherence_messages': 0
        }
        
        self._setup_cache_handlers()
    
    def _setup_cache_handlers(self):
        """Setup cache-specific message handlers."""
        self.message_passing.register_handler(
            MessageType.CACHE_GET,
            self._handle_cache_get
        )
        self.message_passing.register_handler(
            MessageType.CACHE_PUT,
            self._handle_cache_put
        )
        self.message_passing.register_handler(
            MessageType.CACHE_INVALIDATE,
            self._handle_cache_invalidate
        )
        self.message_passing.register_handler(
            MessageType.CACHE_UPDATE,
            self._handle_cache_update
        )
    
    async def start(self):
        """Start the cache node."""
        await super().start()
        logger.info(f"Cache Node {self.node_id} started with {self.coherence_protocol} protocol")
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.
        
        Implements MESI protocol for reads:
        - If in M/E/S state: return value (hit)
        - If in I state or not present: fetch from other nodes (miss)
        """
        entry = self.cache.get(key)
        
        if entry and entry.state != CacheState.INVALID:
            self.stats['hits'] += 1
            await self.metrics.increment_counter('cache_hits')
            logger.debug(f"Cache hit for key {key} in state {entry.state.value}")
            return entry.value
        
        self.stats['misses'] += 1
        await self.metrics.increment_counter('cache_misses')
        logger.debug(f"Cache miss for key {key}")
        
        value = await self._fetch_from_other_nodes(key)
        
        if value is not None:
            self.cache.put(key, value, CacheState.SHARED)
            await self._update_directory(key, CacheState.SHARED)
        
        return value
    
    async def put(self, key: str, value: Any) -> bool:
        """
        Put value in cache.
        
        Implements MESI protocol for writes:
        - Invalidate copies in other nodes
        - Set local state to MODIFIED
        """
        await self._invalidate_other_nodes(key)
        
        self.cache.put(key, value, CacheState.MODIFIED)
        await self._update_directory(key, CacheState.MODIFIED)
        
        await self.metrics.increment_counter('cache_writes')
        logger.debug(f"Put key {key} in cache with MODIFIED state")
        
        return True
    
    async def invalidate(self, key: str) -> bool:
        """Invalidate a cache entry."""
        self.cache.invalidate(key)
        await self._update_directory(key, CacheState.INVALID)
        
        self.stats['invalidations'] += 1
        await self.metrics.increment_counter('cache_invalidations')
        
        logger.debug(f"Invalidated key {key}")
        return True
    
    async def _fetch_from_other_nodes(self, key: str) -> Optional[Any]:
        """Fetch value from other cache nodes."""
        tasks = []
        
        for node in self.cluster_nodes:
            if node['id'] != self.node_id:
                msg = Message(
                    msg_type=MessageType.CACHE_GET,
                    sender_id=self.node_id,
                    receiver_id=node['id'],
                    payload={'key': key, 'probe': True}
                )
                task = self.message_passing.send_message(
                    node['host'], node['port'], msg
                )
                tasks.append(task)
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, dict) and result.get('found'):
                    self.stats['coherence_messages'] += 1
                    return result.get('value')
        
        return None
    
    async def _invalidate_other_nodes(self, key: str):
        """Send invalidation messages to other nodes."""
        tasks = []
        
        for node in self.cluster_nodes:
            if node['id'] != self.node_id:
                msg = Message(
                    msg_type=MessageType.CACHE_INVALIDATE,
                    sender_id=self.node_id,
                    receiver_id=node['id'],
                    payload={'key': key}
                )
                task = self.message_passing.send_message(
                    node['host'], node['port'], msg
                )
                tasks.append(task)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            self.stats['coherence_messages'] += len(tasks)
    
    async def _update_directory(self, key: str, state: CacheState):
        """Update directory entry for cache coherence."""
        if key not in self.directory:
            self.directory[key] = {}
        
        self.directory[key][self.node_id] = state
        
        for node in self.cluster_nodes:
            if node['id'] != self.node_id:
                msg = Message(
                    msg_type=MessageType.CACHE_UPDATE,
                    sender_id=self.node_id,
                    receiver_id=node['id'],
                    payload={
                        'key': key,
                        'node_id': self.node_id,
                        'state': state.value
                    }
                )
                asyncio.create_task(
                    self.message_passing.send_message(
                        node['host'], node['port'], msg
                    )
                )
    
    async def _handle_cache_get(self, message: Message) -> Dict[str, Any]:
        """Handle cache get request."""
        key = message.payload['key']
        is_probe = message.payload.get('probe', False)
        
        entry = self.cache.get(key)
        
        if entry and entry.state != CacheState.INVALID:
            if is_probe and entry.state == CacheState.EXCLUSIVE:
                entry.state = CacheState.SHARED
                await self._update_directory(key, CacheState.SHARED)
            
            return {
                'found': True,
                'value': entry.value,
                'state': entry.state.value
            }
        
        return {'found': False}
    
    async def _handle_cache_put(self, message: Message) -> Dict[str, Any]:
        """Handle cache put request."""
        key = message.payload['key']
        value = message.payload['value']
        
        success = await self.put(key, value)
        
        return {'success': success}
    
    async def _handle_cache_invalidate(self, message: Message) -> Dict[str, Any]:
        """Handle cache invalidation request."""
        key = message.payload['key']
        
        success = await self.invalidate(key)
        
        return {'success': success}
    
    async def _handle_cache_update(self, message: Message) -> Dict[str, Any]:
        """Handle directory update message."""
        key = message.payload['key']
        node_id = message.payload['node_id']
        state = CacheState(message.payload['state'])
        
        if key not in self.directory:
            self.directory[key] = {}
        
        self.directory[key][node_id] = state
        
        return {'success': True}
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_requests = self.stats['hits'] + self.stats['misses']
        hit_rate = self.stats['hits'] / total_requests if total_requests > 0 else 0
        
        return {
            'hits': self.stats['hits'],
            'misses': self.stats['misses'],
            'hit_rate': hit_rate,
            'invalidations': self.stats['invalidations'],
            'evictions': self.stats['evictions'],
            'coherence_messages': self.stats['coherence_messages'],
            'size': self.cache.size(),
            'capacity': self.cache.capacity
        }
    
    def get_directory_info(self, key: str) -> Optional[Dict[str, str]]:
        """Get directory information for a key."""
        if key not in self.directory:
            return None
        
        return {
            node_id: state.value
            for node_id, state in self.directory[key].items()
        }
    
    def get_status(self) -> Dict[str, Any]:
        """Get cache node status."""
        base_status = super().get_status()
        
        return {
            **base_status,
            'cache_stats': self.get_cache_stats(),
            'coherence_protocol': self.coherence_protocol,
            'replacement_policy': self.replacement_policy
        }
