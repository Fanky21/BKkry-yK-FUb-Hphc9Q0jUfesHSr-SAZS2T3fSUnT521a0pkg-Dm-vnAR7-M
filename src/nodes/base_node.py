"""Base node implementation for distributed system."""

import asyncio
import logging
from typing import Optional, Dict, Any
from src.utils.config import Config
from src.utils.metrics import MetricsCollector
from src.communication.message_passing import MessagePassing, MessageType
from src.communication.failure_detector import FailureDetector, NodeStatus


logger = logging.getLogger(__name__)


class BaseNode:
    """Base class for all distributed nodes."""
    
    def __init__(self, config: Config):
        self.config = config
        self.node_id = config.node_id
        self.host = config.node_host
        self.port = config.node_port
        
        self.message_passing = MessagePassing(self.node_id, self.host, self.port)
        self.failure_detector = FailureDetector(
            self.node_id,
            heartbeat_interval=config.heartbeat_interval
        )
        self.metrics = MetricsCollector()
        
        self.running = False
        self.cluster_nodes: list = []
        
        self._heartbeat_task: Optional[asyncio.Task] = None
        
        self._setup_message_handlers()
        self._setup_cluster()
    
    def _setup_message_handlers(self):
        """Setup message handlers for base node."""
        self.message_passing.register_handler(
            MessageType.HEARTBEAT,
            self._handle_heartbeat
        )
        self.message_passing.register_handler(
            MessageType.PING,
            self._handle_ping
        )
    
    def _setup_cluster(self):
        """Setup cluster configuration."""
        for node in self.config.cluster_nodes:
            node_info = {
                'id': f"{node['host']}:{node['port']}",
                'host': node['host'],
                'port': node['port']
            }
            self.cluster_nodes.append(node_info)
            self.failure_detector.add_node(
                node_info['id'],
                node_info['host'],
                node_info['port']
            )
    
    async def start(self):
        """Start the node."""
        logger.info(f"Starting node {self.node_id}")
        
        self.running = True
        
        await self.message_passing.start()
        await self.failure_detector.start()
        
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        logger.info(f"Node {self.node_id} started successfully")
    
    async def stop(self):
        """Stop the node."""
        logger.info(f"Stopping node {self.node_id}")
        
        self.running = False
        
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        await self.failure_detector.stop()
        await self.message_passing.stop()
        
        logger.info(f"Node {self.node_id} stopped")
    
    async def _heartbeat_loop(self):
        """Send periodic heartbeats to other nodes."""
        while self.running:
            try:
                await self._send_heartbeats()
                await asyncio.sleep(self.config.heartbeat_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}", exc_info=True)
    
    async def _send_heartbeats(self):
        """Send heartbeat messages to all cluster nodes."""
        from src.communication.message_passing import Message
        
        message = Message(
            msg_type=MessageType.HEARTBEAT,
            sender_id=self.node_id,
            receiver_id="",
            payload={'timestamp': asyncio.get_event_loop().time()}
        )
        
        await self.message_passing.broadcast_message(self.cluster_nodes, message)
    
    async def _handle_heartbeat(self, message) -> Dict[str, Any]:
        """Handle heartbeat message."""
        self.failure_detector.update_heartbeat(message.sender_id)
        await self.metrics.increment_counter('heartbeats_received')
        return {'status': 'ok'}
    
    async def _handle_ping(self, message) -> Dict[str, Any]:
        """Handle ping message."""
        return {
            'status': 'ok',
            'node_id': self.node_id,
            'timestamp': asyncio.get_event_loop().time()
        }
    
    def get_status(self) -> Dict[str, Any]:
        """Get node status."""
        return {
            'node_id': self.node_id,
            'host': self.host,
            'port': self.port,
            'running': self.running,
            'cluster_size': len(self.cluster_nodes),
            'cluster_health': self.failure_detector.get_cluster_health()
        }
