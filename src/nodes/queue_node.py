"""
Distributed Queue System with consistent hashing and persistence.
Supports multiple producers/consumers with at-least-once delivery.
"""

import asyncio
import hashlib
import json
import logging
import os
import pickle
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import deque
import time

from src.nodes.base_node import BaseNode
from src.utils.config import Config
from src.communication.message_passing import Message, MessageType


logger = logging.getLogger(__name__)


@dataclass
class QueueMessage:
    """Message in the distributed queue."""
    message_id: str
    payload: Any
    timestamp: float = field(default_factory=time.time)
    retries: int = 0
    max_retries: int = 3
    ack_timeout: float = 30.0
    
    def to_dict(self) -> Dict:
        return {
            'message_id': self.message_id,
            'payload': self.payload,
            'timestamp': self.timestamp,
            'retries': self.retries,
            'max_retries': self.max_retries,
            'ack_timeout': self.ack_timeout
        }


class ConsistentHash:
    """Consistent hashing ring for queue distribution."""
    
    def __init__(self, nodes: List[str], virtual_nodes: int = 150):
        self.virtual_nodes = virtual_nodes
        self.ring: Dict[int, str] = {}
        self.nodes: set = set()
        
        for node in nodes:
            self.add_node(node)
    
    def _hash(self, key: str) -> int:
        """Hash a key to a position on the ring."""
        return int(hashlib.md5(key.encode()).hexdigest(), 16)
    
    def add_node(self, node: str):
        """Add a node to the ring."""
        self.nodes.add(node)
        for i in range(self.virtual_nodes):
            virtual_key = f"{node}:{i}"
            hash_value = self._hash(virtual_key)
            self.ring[hash_value] = node
    
    def remove_node(self, node: str):
        """Remove a node from the ring."""
        self.nodes.discard(node)
        keys_to_remove = [k for k, v in self.ring.items() if v == node]
        for key in keys_to_remove:
            del self.ring[key]
    
    def get_node(self, key: str) -> Optional[str]:
        """Get the node responsible for a key."""
        if not self.ring:
            return None
        
        hash_value = self._hash(key)
        
        for ring_hash in sorted(self.ring.keys()):
            if hash_value <= ring_hash:
                return self.ring[ring_hash]
        
        return self.ring[min(self.ring.keys())]
    
    def get_replicas(self, key: str, count: int = 3) -> List[str]:
        """Get multiple nodes for replication."""
        if not self.ring or count <= 0:
            return []
        
        hash_value = self._hash(key)
        sorted_hashes = sorted(self.ring.keys())
        
        start_idx = 0
        for i, ring_hash in enumerate(sorted_hashes):
            if hash_value <= ring_hash:
                start_idx = i
                break
        
        replicas = []
        checked = 0
        idx = start_idx
        
        while len(replicas) < count and checked < len(sorted_hashes):
            node = self.ring[sorted_hashes[idx]]
            if node not in replicas:
                replicas.append(node)
            idx = (idx + 1) % len(sorted_hashes)
            checked += 1
        
        return replicas


class QueueNode(BaseNode):
    """
    Distributed Queue Node.
    
    Features:
    - Consistent hashing for distribution
    - Message persistence
    - At-least-once delivery
    - Automatic retry on failure
    - Node failure recovery
    """
    
    def __init__(self, config: Config):
        super().__init__(config)
        
        self.queues: Dict[str, deque] = {}
        self.in_flight: Dict[str, QueueMessage] = {}
        self.persistent_queue: Dict[str, List[Dict]] = {}
        
        node_ids = [n['id'] for n in self.cluster_nodes] + [self.node_id]
        self.hash_ring = ConsistentHash(node_ids)
        
        self.persist_dir = config.queue_persist_dir
        os.makedirs(self.persist_dir, exist_ok=True)
        
        self.batch_size = config.queue_batch_size
        self.flush_interval = config.queue_flush_interval
        
        self._flush_task: Optional[asyncio.Task] = None
        self._retry_task: Optional[asyncio.Task] = None
        
        self._setup_queue_handlers()
        
        self._load_persisted_messages()
    
    def _setup_queue_handlers(self):
        """Setup queue-specific message handlers."""
        self.message_passing.register_handler(
            MessageType.ENQUEUE,
            self._handle_enqueue
        )
        self.message_passing.register_handler(
            MessageType.DEQUEUE,
            self._handle_dequeue
        )
        self.message_passing.register_handler(
            MessageType.QUEUE_ACK,
            self._handle_ack
        )
    
    async def start(self):
        """Start the queue node."""
        await super().start()
        
        self._flush_task = asyncio.create_task(self._flush_loop())
        self._retry_task = asyncio.create_task(self._retry_loop())
        
        logger.info(f"Queue Node {self.node_id} started")
    
    async def stop(self):
        """Stop the queue node."""
        if self._flush_task:
            self._flush_task.cancel()
        if self._retry_task:
            self._retry_task.cancel()
        
        await self._flush_to_disk()
        await super().stop()
        
        logger.info(f"Queue Node {self.node_id} stopped")
    
    async def enqueue(self, queue_name: str, message: Any) -> bool:
        """
        Enqueue a message.
        
        Args:
            queue_name: Name of the queue
            message: Message payload
            
        Returns:
            True if successfully enqueued
        """
        responsible_nodes = self.hash_ring.get_replicas(queue_name, count=3)
        
        if self.node_id not in responsible_nodes:
            for node_id in responsible_nodes:
                if node_id != self.node_id:
                    node = next((n for n in self.cluster_nodes if n['id'] == node_id), None)
                    if node:
                        msg = Message(
                            msg_type=MessageType.ENQUEUE,
                            sender_id=self.node_id,
                            receiver_id=node_id,
                            payload={'queue_name': queue_name, 'message': message}
                        )
                        result = await self.message_passing.send_message(
                            node['host'], node['port'], msg
                        )
                        if result and result.get('success'):
                            return True
            return False
        
        msg_id = f"{self.node_id}:{time.time_ns()}"
        queue_msg = QueueMessage(message_id=msg_id, payload=message)
        
        if queue_name not in self.queues:
            self.queues[queue_name] = deque()
        
        self.queues[queue_name].append(queue_msg)
        
        await self.metrics.increment_counter('messages_enqueued', 
                                             labels={'queue': queue_name})
        
        logger.debug(f"Enqueued message {msg_id} to {queue_name}")
        
        await self._replicate_message(queue_name, queue_msg, responsible_nodes)
        
        return True
    
    async def dequeue(self, queue_name: str, consumer_id: str) -> Optional[Dict]:
        """
        Dequeue a message.
        
        Args:
            queue_name: Name of the queue
            consumer_id: ID of the consumer
            
        Returns:
            Message dict if available, None otherwise
        """
        if queue_name not in self.queues or not self.queues[queue_name]:
            return None
        
        queue_msg = self.queues[queue_name].popleft()
        
        self.in_flight[queue_msg.message_id] = queue_msg
        
        await self.metrics.increment_counter('messages_dequeued',
                                             labels={'queue': queue_name})
        
        logger.debug(f"Dequeued message {queue_msg.message_id} from {queue_name}")
        
        return queue_msg.to_dict()
    
    async def acknowledge(self, message_id: str) -> bool:
        """
        Acknowledge message delivery.
        
        Args:
            message_id: ID of the message to acknowledge
            
        Returns:
            True if acknowledged
        """
        if message_id in self.in_flight:
            del self.in_flight[message_id]
            await self.metrics.increment_counter('messages_acknowledged')
            logger.debug(f"Acknowledged message {message_id}")
            return True
        
        return False
    
    async def _replicate_message(self, queue_name: str, message: QueueMessage, 
                                 nodes: List[str]):
        """Replicate message to other nodes for fault tolerance."""
        tasks = []
        for node_id in nodes:
            if node_id != self.node_id:
                node = next((n for n in self.cluster_nodes if n['id'] == node_id), None)
                if node:
                    msg = Message(
                        msg_type=MessageType.ENQUEUE,
                        sender_id=self.node_id,
                        receiver_id=node_id,
                        payload={
                            'queue_name': queue_name,
                            'message': message.payload,
                            'replicate': True
                        }
                    )
                    task = self.message_passing.send_message(
                        node['host'], node['port'], msg
                    )
                    tasks.append(task)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _handle_enqueue(self, message: Message) -> Dict[str, Any]:
        """Handle enqueue message."""
        queue_name = message.payload['queue_name']
        msg_payload = message.payload['message']
        is_replica = message.payload.get('replicate', False)
        
        if is_replica or await self.enqueue(queue_name, msg_payload):
            return {'success': True}
        return {'success': False}
    
    async def _handle_dequeue(self, message: Message) -> Dict[str, Any]:
        """Handle dequeue message."""
        queue_name = message.payload['queue_name']
        consumer_id = message.payload['consumer_id']
        
        msg = await self.dequeue(queue_name, consumer_id)
        
        return {'success': msg is not None, 'message': msg}
    
    async def _handle_ack(self, message: Message) -> Dict[str, Any]:
        """Handle acknowledgment message."""
        message_id = message.payload['message_id']
        success = await self.acknowledge(message_id)
        return {'success': success}
    
    async def _flush_loop(self):
        """Periodically flush messages to disk."""
        while self.running:
            try:
                await asyncio.sleep(self.flush_interval)
                await self._flush_to_disk()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in flush loop: {e}", exc_info=True)
    
    async def _flush_to_disk(self):
        """Flush messages to persistent storage."""
        for queue_name, queue in self.queues.items():
            if queue:
                filepath = os.path.join(self.persist_dir, f"{queue_name}.pkl")
                try:
                    with open(filepath, 'wb') as f:
                        pickle.dump(list(queue), f)
                    logger.debug(f"Flushed {len(queue)} messages from {queue_name}")
                except Exception as e:
                    logger.error(f"Error flushing queue {queue_name}: {e}")
    
    def _load_persisted_messages(self):
        """Load persisted messages from disk."""
        if not os.path.exists(self.persist_dir):
            return
        
        for filename in os.listdir(self.persist_dir):
            if filename.endswith('.pkl'):
                queue_name = filename[:-4]
                filepath = os.path.join(self.persist_dir, filename)
                
                try:
                    with open(filepath, 'rb') as f:
                        messages = pickle.load(f)
                        self.queues[queue_name] = deque(messages)
                        logger.info(f"Loaded {len(messages)} messages for {queue_name}")
                except Exception as e:
                    logger.error(f"Error loading queue {queue_name}: {e}")
    
    async def _retry_loop(self):
        """Retry unacknowledged messages."""
        while self.running:
            try:
                await asyncio.sleep(5.0)
                await self._retry_unacknowledged()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in retry loop: {e}", exc_info=True)
    
    async def _retry_unacknowledged(self):
        """Retry messages that weren't acknowledged."""
        current_time = time.time()
        to_retry = []
        
        for msg_id, queue_msg in list(self.in_flight.items()):
            if current_time - queue_msg.timestamp > queue_msg.ack_timeout:
                if queue_msg.retries < queue_msg.max_retries:
                    queue_msg.retries += 1
                    to_retry.append((msg_id, queue_msg))
                    del self.in_flight[msg_id]
                    logger.warning(f"Retrying message {msg_id} (attempt {queue_msg.retries})")
                else:
                    del self.in_flight[msg_id]
                    await self.metrics.increment_counter('messages_failed')
                    logger.error(f"Message {msg_id} exceeded max retries")
        
        for msg_id, queue_msg in to_retry:
            for queue in self.queues.values():
                queue.append(queue_msg)
                break
    
    def get_queue_status(self, queue_name: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific queue."""
        if queue_name not in self.queues:
            return None
        
        return {
            'queue_name': queue_name,
            'size': len(self.queues[queue_name]),
            'in_flight': sum(1 for msg in self.in_flight.values()),
            'responsible_nodes': self.hash_ring.get_replicas(queue_name, 3)
        }
    
    def get_status(self) -> Dict[str, Any]:
        """Get queue node status."""
        base_status = super().get_status()
        
        return {
            **base_status,
            'total_queues': len(self.queues),
            'total_messages': sum(len(q) for q in self.queues.values()),
            'in_flight_messages': len(self.in_flight)
        }
