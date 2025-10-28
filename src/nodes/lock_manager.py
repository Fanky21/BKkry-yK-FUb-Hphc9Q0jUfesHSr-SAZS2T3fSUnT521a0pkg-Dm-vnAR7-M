"""
Distributed Lock Manager using Raft consensus.
Supports shared and exclusive locks with deadlock detection.
"""

import asyncio
import logging
import time
from typing import Dict, Set, Optional, List
from enum import Enum
from dataclasses import dataclass, field
from collections import defaultdict

from src.nodes.base_node import BaseNode
from src.consensus.raft import RaftNode, RaftConfig
from src.communication.message_passing import Message, MessageType
from src.utils.config import Config


logger = logging.getLogger(__name__)


class LockType(Enum):
    """Types of distributed locks."""
    SHARED = "shared"
    EXCLUSIVE = "exclusive"


@dataclass
class LockRequest:
    """Represents a lock request."""
    resource_id: str
    client_id: str
    lock_type: LockType
    request_time: float = field(default_factory=time.time)
    timeout: float = 30.0


@dataclass
class LockInfo:
    """Information about a lock."""
    resource_id: str
    lock_type: LockType
    holders: Set[str] = field(default_factory=set)
    waiting: List[LockRequest] = field(default_factory=list)
    acquired_time: float = field(default_factory=time.time)


class DeadlockDetector:
    """Detects deadlocks in distributed lock requests."""
    
    def __init__(self):
        self.wait_for_graph: Dict[str, Set[str]] = defaultdict(set)
    
    def add_wait(self, waiter: str, holder: str):
        """Add a wait-for relationship."""
        self.wait_for_graph[waiter].add(holder)
    
    def remove_wait(self, waiter: str, holder: Optional[str] = None):
        """Remove a wait-for relationship."""
        if holder:
            self.wait_for_graph[waiter].discard(holder)
        else:
            self.wait_for_graph.pop(waiter, None)
    
    def detect_deadlock(self) -> Optional[List[str]]:
        """
        Detect deadlock using cycle detection in wait-for graph.
        Returns the cycle if found, None otherwise.
        """
        visited = set()
        rec_stack = set()
        path = []
        
        def dfs(node: str) -> Optional[List[str]]:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            
            for neighbor in self.wait_for_graph.get(node, set()):
                if neighbor not in visited:
                    cycle = dfs(neighbor)
                    if cycle:
                        return cycle
                elif neighbor in rec_stack:
                    cycle_start = path.index(neighbor)
                    return path[cycle_start:]
            
            rec_stack.remove(node)
            path.pop()
            return None
        
        for node in self.wait_for_graph:
            if node not in visited:
                cycle = dfs(node)
                if cycle:
                    return cycle
        
        return None
    
    def get_graph(self) -> Dict[str, Set[str]]:
        """Get the wait-for graph."""
        return dict(self.wait_for_graph)


class LockManager(BaseNode):
    """
    Distributed Lock Manager.
    
    Features:
    - Shared and exclusive locks
    - Raft-based consensus for consistency
    - Deadlock detection
    - Lock timeout and automatic release
    - Network partition handling
    """
    
    def __init__(self, config: Config):
        super().__init__(config)
        
        raft_config = RaftConfig(
            election_timeout_min=config.election_timeout_min,
            election_timeout_max=config.election_timeout_max,
            heartbeat_interval=config.heartbeat_interval
        )
        self.raft = RaftNode(self.node_id, self.cluster_nodes, raft_config)
        self.raft.on_commit_callback = self._apply_lock_operation
        
        self.locks: Dict[str, LockInfo] = {}
        self.client_locks: Dict[str, Set[str]] = defaultdict(set)
        
        self.deadlock_detector = DeadlockDetector()
        
        self._deadlock_detection_task: Optional[asyncio.Task] = None
        self._timeout_checker_task: Optional[asyncio.Task] = None
        
        self._setup_lock_handlers()
    
    def _setup_lock_handlers(self):
        """Setup lock-specific message handlers."""
        self.message_passing.register_handler(
            MessageType.LOCK_REQUEST,
            self._handle_lock_request_message
        )
        self.message_passing.register_handler(
            MessageType.LOCK_RELEASE,
            self._handle_lock_release_message
        )
        self.message_passing.register_handler(
            MessageType.APPEND_ENTRIES,
            self.raft.handle_append_entries
        )
        self.message_passing.register_handler(
            MessageType.REQUEST_VOTE,
            self.raft.handle_request_vote
        )
    
    async def start(self):
        """Start the lock manager."""
        await super().start()
        await self.raft.start()
        
        self._deadlock_detection_task = asyncio.create_task(
            self._deadlock_detection_loop()
        )
        self._timeout_checker_task = asyncio.create_task(
            self._timeout_checker_loop()
        )
        
        logger.info(f"Lock Manager {self.node_id} started")
    
    async def stop(self):
        """Stop the lock manager."""
        if self._deadlock_detection_task:
            self._deadlock_detection_task.cancel()
            try:
                await self._deadlock_detection_task
            except asyncio.CancelledError:
                pass
        
        if self._timeout_checker_task:
            self._timeout_checker_task.cancel()
            try:
                await self._timeout_checker_task
            except asyncio.CancelledError:
                pass
        
        await self.raft.stop()
        await super().stop()
        
        logger.info(f"Lock Manager {self.node_id} stopped")
    
    async def acquire_lock(self, resource_id: str, client_id: str, 
                          lock_type: LockType = LockType.EXCLUSIVE,
                          timeout: float = 30.0) -> bool:
        """
        Acquire a lock on a resource.
        
        Args:
            resource_id: ID of the resource to lock
            client_id: ID of the client requesting the lock
            lock_type: Type of lock (SHARED or EXCLUSIVE)
            timeout: Lock timeout in seconds
            
        Returns:
            True if lock acquired, False otherwise
        """
        if not self.raft.is_leader():
            logger.warning(f"Not leader, cannot acquire lock for {resource_id}")
            return False
        
        request = LockRequest(
            resource_id=resource_id,
            client_id=client_id,
            lock_type=lock_type,
            timeout=timeout
        )
        
        command = {
            'operation': 'acquire',
            'resource_id': resource_id,
            'client_id': client_id,
            'lock_type': lock_type.value,
            'timeout': timeout
        }
        
        success = await self.raft.append_entry(command)
        
        if success:
            await self.metrics.increment_counter('locks_acquired', 
                                                 labels={'type': lock_type.value})
        
        return success
    
    async def release_lock(self, resource_id: str, client_id: str) -> bool:
        """
        Release a lock on a resource.
        
        Args:
            resource_id: ID of the resource to unlock
            client_id: ID of the client releasing the lock
            
        Returns:
            True if lock released, False otherwise
        """
        if not self.raft.is_leader():
            logger.warning(f"Not leader, cannot release lock for {resource_id}")
            return False
        
        command = {
            'operation': 'release',
            'resource_id': resource_id,
            'client_id': client_id
        }
        
        success = await self.raft.append_entry(command)
        
        if success:
            await self.metrics.increment_counter('locks_released')
        
        return success
    
    def _apply_lock_operation(self, command: Dict[str, any]):
        """Apply a committed lock operation."""
        operation = command.get('operation')
        
        if operation == 'acquire':
            self._do_acquire_lock(
                command['resource_id'],
                command['client_id'],
                LockType(command['lock_type']),
                command.get('timeout', 30.0)
            )
        elif operation == 'release':
            self._do_release_lock(
                command['resource_id'],
                command['client_id']
            )
    
    def _do_acquire_lock(self, resource_id: str, client_id: str, 
                        lock_type: LockType, timeout: float):
        """Actually acquire the lock (after consensus)."""
        if resource_id not in self.locks:
            self.locks[resource_id] = LockInfo(
                resource_id=resource_id,
                lock_type=lock_type,
                holders={client_id}
            )
            self.client_locks[client_id].add(resource_id)
            logger.info(f"Granted {lock_type.value} lock on {resource_id} to {client_id}")
        else:
            lock_info = self.locks[resource_id]
            
            can_grant = False
            
            if lock_type == LockType.SHARED and lock_info.lock_type == LockType.SHARED:
                can_grant = True
            elif not lock_info.holders:
                can_grant = True
            
            if can_grant:
                lock_info.holders.add(client_id)
                lock_info.lock_type = lock_type
                self.client_locks[client_id].add(resource_id)
                logger.info(f"Granted {lock_type.value} lock on {resource_id} to {client_id}")
            else:
                request = LockRequest(
                    resource_id=resource_id,
                    client_id=client_id,
                    lock_type=lock_type,
                    timeout=timeout
                )
                lock_info.waiting.append(request)
                
                for holder in lock_info.holders:
                    self.deadlock_detector.add_wait(client_id, holder)
                
                logger.info(f"Client {client_id} waiting for lock on {resource_id}")
    
    def _do_release_lock(self, resource_id: str, client_id: str):
        """Actually release the lock (after consensus)."""
        if resource_id not in self.locks:
            logger.warning(f"Attempted to release non-existent lock {resource_id}")
            return
        
        lock_info = self.locks[resource_id]
        
        if client_id not in lock_info.holders:
            logger.warning(f"Client {client_id} does not hold lock {resource_id}")
            return
        
        lock_info.holders.remove(client_id)
        self.client_locks[client_id].discard(resource_id)
        self.deadlock_detector.remove_wait(client_id)
        
        logger.info(f"Released lock on {resource_id} from {client_id}")
        
        if not lock_info.holders and lock_info.waiting:
            self._grant_waiting_locks(resource_id)
        
        if not lock_info.holders and not lock_info.waiting:
            del self.locks[resource_id]
    
    def _grant_waiting_locks(self, resource_id: str):
        """Grant locks to waiting clients."""
        if resource_id not in self.locks:
            return
        
        lock_info = self.locks[resource_id]
        
        while lock_info.waiting:
            request = lock_info.waiting[0]
            
            can_grant = False
            
            if request.lock_type == LockType.SHARED:
                if not lock_info.holders or lock_info.lock_type == LockType.SHARED:
                    can_grant = True
            else:
                if not lock_info.holders:
                    can_grant = True
            
            if can_grant:
                lock_info.waiting.pop(0)
                lock_info.holders.add(request.client_id)
                lock_info.lock_type = request.lock_type
                self.client_locks[request.client_id].add(resource_id)
                self.deadlock_detector.remove_wait(request.client_id)
                logger.info(f"Granted waiting lock on {resource_id} to {request.client_id}")
                
                if request.lock_type == LockType.EXCLUSIVE:
                    break
            else:
                break
    
    async def _deadlock_detection_loop(self):
        """Periodically check for deadlocks."""
        while self.running:
            try:
                await asyncio.sleep(self.config.deadlock_detection_interval)
                await self._detect_and_resolve_deadlocks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in deadlock detection: {e}", exc_info=True)
    
    async def _detect_and_resolve_deadlocks(self):
        """Detect and resolve deadlocks."""
        cycle = self.deadlock_detector.detect_deadlock()
        
        if cycle:
            logger.warning(f"Deadlock detected: {' -> '.join(cycle)}")
            await self.metrics.increment_counter('deadlocks_detected')
            
            victim = cycle[-1]
            
            if victim in self.client_locks:
                resources = list(self.client_locks[victim])
                for resource_id in resources:
                    await self.release_lock(resource_id, victim)
                
                logger.info(f"Resolved deadlock by aborting {victim}")
                await self.metrics.increment_counter('deadlocks_resolved')
    
    async def _timeout_checker_loop(self):
        """Check for timed out locks."""
        while self.running:
            try:
                await asyncio.sleep(1.0)
                await self._check_lock_timeouts()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in timeout checker: {e}", exc_info=True)
    
    async def _check_lock_timeouts(self):
        """Check and release timed out locks."""
        current_time = time.time()
        timed_out = []
        
        for resource_id, lock_info in self.locks.items():
            for request in lock_info.waiting[:]:
                if current_time - request.request_time > request.timeout:
                    lock_info.waiting.remove(request)
                    self.deadlock_detector.remove_wait(request.client_id)
                    logger.info(f"Lock request timeout: {request.client_id} for {resource_id}")
                    await self.metrics.increment_counter('lock_timeouts')
    
    async def _handle_lock_request_message(self, message: Message) -> Dict[str, any]:
        """Handle lock request message."""
        resource_id = message.payload['resource_id']
        client_id = message.payload['client_id']
        lock_type = LockType(message.payload['lock_type'])
        timeout = message.payload.get('timeout', 30.0)
        
        success = await self.acquire_lock(resource_id, client_id, lock_type, timeout)
        
        return {'success': success}
    
    async def _handle_lock_release_message(self, message: Message) -> Dict[str, any]:
        """Handle lock release message."""
        resource_id = message.payload['resource_id']
        client_id = message.payload['client_id']
        
        success = await self.release_lock(resource_id, client_id)
        
        return {'success': success}
    
    def get_lock_status(self, resource_id: str) -> Optional[Dict[str, any]]:
        """Get status of a lock."""
        if resource_id not in self.locks:
            return None
        
        lock_info = self.locks[resource_id]
        return {
            'resource_id': resource_id,
            'lock_type': lock_info.lock_type.value,
            'holders': list(lock_info.holders),
            'waiting_count': len(lock_info.waiting),
            'acquired_time': lock_info.acquired_time
        }
    
    def get_status(self) -> Dict[str, any]:
        """Get lock manager status."""
        base_status = super().get_status()
        
        return {
            **base_status,
            'raft': self.raft.get_status(),
            'total_locks': len(self.locks),
            'total_waiting': sum(len(lock.waiting) for lock in self.locks.values()),
            'deadlock_graph': self.deadlock_detector.get_graph()
        }
