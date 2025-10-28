"""Failure detector for monitoring node health in the distributed system."""

import asyncio
import time
import logging
from typing import Dict, Set, Callable, Optional
from enum import Enum
from dataclasses import dataclass


logger = logging.getLogger(__name__)


class NodeStatus(Enum):
    """Status of a node."""
    ALIVE = "alive"
    SUSPECTED = "suspected"
    DEAD = "dead"
    UNKNOWN = "unknown"


@dataclass
class NodeHealth:
    """Health information for a node."""
    node_id: str
    host: str
    port: int
    status: NodeStatus = NodeStatus.UNKNOWN
    last_heartbeat: float = 0.0
    missed_heartbeats: int = 0
    latency: float = 0.0


class FailureDetector:
    """
    Failure detector using heartbeat mechanism.
    Implements Eventually Perfect Failure Detector (◊P).
    """
    
    def __init__(self, node_id: str, heartbeat_interval: float = 1.0,
                 timeout_multiplier: float = 3.0, suspected_threshold: int = 2):
        self.node_id = node_id
        self.heartbeat_interval = heartbeat_interval
        self.timeout = heartbeat_interval * timeout_multiplier
        self.suspected_threshold = suspected_threshold
        
        self.nodes: Dict[str, NodeHealth] = {}
        self.status_change_callbacks: list[Callable] = []
        
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
    
    def add_node(self, node_id: str, host: str, port: int):
        """Add a node to monitor."""
        if node_id != self.node_id:
            self.nodes[node_id] = NodeHealth(
                node_id=node_id,
                host=host,
                port=port,
                status=NodeStatus.UNKNOWN
            )
            logger.info(f"Added node {node_id} to failure detector")
    
    def remove_node(self, node_id: str):
        """Remove a node from monitoring."""
        if node_id in self.nodes:
            del self.nodes[node_id]
            logger.info(f"Removed node {node_id} from failure detector")
    
    def update_heartbeat(self, node_id: str):
        """Update heartbeat timestamp for a node."""
        if node_id in self.nodes:
            node = self.nodes[node_id]
            current_time = time.time()
            
            if node.last_heartbeat > 0:
                node.latency = current_time - node.last_heartbeat
            
            node.last_heartbeat = current_time
            node.missed_heartbeats = 0
            
            old_status = node.status
            node.status = NodeStatus.ALIVE
            
            if old_status != NodeStatus.ALIVE:
                logger.info(f"Node {node_id} is now {NodeStatus.ALIVE}")
                self._notify_status_change(node_id, old_status, NodeStatus.ALIVE)
    
    def get_node_status(self, node_id: str) -> NodeStatus:
        """Get the current status of a node."""
        if node_id in self.nodes:
            return self.nodes[node_id].status
        return NodeStatus.UNKNOWN
    
    def get_alive_nodes(self) -> Set[str]:
        """Get set of nodes that are currently alive."""
        return {
            node_id for node_id, health in self.nodes.items()
            if health.status == NodeStatus.ALIVE
        }
    
    def get_suspected_nodes(self) -> Set[str]:
        """Get set of nodes that are suspected to have failed."""
        return {
            node_id for node_id, health in self.nodes.items()
            if health.status == NodeStatus.SUSPECTED
        }
    
    def get_dead_nodes(self) -> Set[str]:
        """Get set of nodes that are confirmed dead."""
        return {
            node_id for node_id, health in self.nodes.items()
            if health.status == NodeStatus.DEAD
        }
    
    def get_all_nodes(self) -> Dict[str, NodeHealth]:
        """Get health information for all nodes."""
        return self.nodes.copy()
    
    def register_status_change_callback(self, callback: Callable):
        """Register a callback for node status changes."""
        self.status_change_callbacks.append(callback)
    
    async def start(self):
        """Start the failure detector."""
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Failure detector started")
    
    async def stop(self):
        """Stop the failure detector."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("Failure detector stopped")
    
    async def _monitor_loop(self):
        """Main monitoring loop to check node health."""
        while self._running:
            try:
                await self._check_nodes()
                await asyncio.sleep(self.heartbeat_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in failure detector monitor loop: {e}", exc_info=True)
    
    async def _check_nodes(self):
        """Check health of all monitored nodes."""
        current_time = time.time()
        
        for node_id, health in self.nodes.items():
            if health.last_heartbeat == 0:
                continue
            
            time_since_heartbeat = current_time - health.last_heartbeat
            
            if time_since_heartbeat > self.timeout:
                health.missed_heartbeats += 1
                old_status = health.status
                
                if health.missed_heartbeats >= self.suspected_threshold * 2:
                    new_status = NodeStatus.DEAD
                elif health.missed_heartbeats >= self.suspected_threshold:
                    new_status = NodeStatus.SUSPECTED
                else:
                    new_status = NodeStatus.ALIVE
                
                if old_status != new_status:
                    health.status = new_status
                    logger.warning(
                        f"Node {node_id} status changed: {old_status} -> {new_status} "
                        f"(missed {health.missed_heartbeats} heartbeats)"
                    )
                    self._notify_status_change(node_id, old_status, new_status)
    
    def _notify_status_change(self, node_id: str, old_status: NodeStatus, new_status: NodeStatus):
        """Notify registered callbacks of status change."""
        for callback in self.status_change_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    asyncio.create_task(callback(node_id, old_status, new_status))
                else:
                    callback(node_id, old_status, new_status)
            except Exception as e:
                logger.error(f"Error in status change callback: {e}", exc_info=True)
    
    def get_cluster_health(self) -> Dict[str, any]:
        """Get overall cluster health statistics."""
        total = len(self.nodes)
        alive = len(self.get_alive_nodes())
        suspected = len(self.get_suspected_nodes())
        dead = len(self.get_dead_nodes())
        
        return {
            'total_nodes': total,
            'alive_nodes': alive,
            'suspected_nodes': suspected,
            'dead_nodes': dead,
            'cluster_healthy': dead == 0 and suspected == 0,
            'availability': alive / total if total > 0 else 0
        }
