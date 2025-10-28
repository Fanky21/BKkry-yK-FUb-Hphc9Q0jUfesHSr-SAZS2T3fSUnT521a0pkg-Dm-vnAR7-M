"""Message passing infrastructure for distributed nodes."""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
import aiohttp
from aiohttp import web
import time


logger = logging.getLogger(__name__)


class MessageType(Enum):
    """Types of messages in the distributed system."""
    REQUEST_VOTE = "request_vote"
    VOTE_RESPONSE = "vote_response"
    APPEND_ENTRIES = "append_entries"
    APPEND_ENTRIES_RESPONSE = "append_entries_response"
    
    LOCK_REQUEST = "lock_request"
    LOCK_RESPONSE = "lock_response"
    LOCK_RELEASE = "lock_release"
    DEADLOCK_DETECTION = "deadlock_detection"
    
    ENQUEUE = "enqueue"
    DEQUEUE = "dequeue"
    QUEUE_ACK = "queue_ack"
    
    CACHE_GET = "cache_get"
    CACHE_PUT = "cache_put"
    CACHE_INVALIDATE = "cache_invalidate"
    CACHE_UPDATE = "cache_update"
    
    HEARTBEAT = "heartbeat"
    PING = "ping"
    PONG = "pong"


@dataclass
class Message:
    """Message structure for inter-node communication."""
    msg_type: MessageType
    sender_id: str
    receiver_id: str
    term: int = 0
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    message_id: str = field(default_factory=lambda: str(time.time_ns()))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary."""
        data = asdict(self)
        data['msg_type'] = self.msg_type.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        """Create message from dictionary."""
        data['msg_type'] = MessageType(data['msg_type'])
        return cls(**data)
    
    def to_json(self) -> str:
        """Convert message to JSON string."""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Message':
        """Create message from JSON string."""
        return cls.from_dict(json.loads(json_str))


class MessagePassing:
    """Handles message passing between distributed nodes."""
    
    def __init__(self, node_id: str, host: str, port: int):
        self.node_id = node_id
        self.host = host
        self.port = port
        self.handlers: Dict[MessageType, Callable] = {}
        self.app = web.Application()
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self.session: Optional[aiohttp.ClientSession] = None
        
        self.app.router.add_post('/message', self._handle_message)
        self.app.router.add_get('/health', self._handle_health)
    
    async def start(self):
        """Start the message passing server."""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=5.0),
            connector=aiohttp.TCPConnector(limit=100)
        )
        
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()
        
        logger.info(f"Message passing server started on {self.host}:{self.port}")
    
    async def stop(self):
        """Stop the message passing server."""
        if self.session:
            await self.session.close()
        
        if self.site:
            await self.site.stop()
        
        if self.runner:
            await self.runner.cleanup()
        
        logger.info("Message passing server stopped")
    
    def register_handler(self, msg_type: MessageType, handler: Callable):
        """Register a message handler for a specific message type."""
        self.handlers[msg_type] = handler
        logger.debug(f"Registered handler for {msg_type}")
    
    async def send_message(self, target_host: str, target_port: int, 
                          message: Message, retry: bool = True) -> Optional[Dict[str, Any]]:
        """Send a message to another node."""
        url = f"http://{target_host}:{target_port}/message"
        max_retries = 3 if retry else 1
        
        for attempt in range(max_retries):
            try:
                async with self.session.post(url, json=message.to_dict()) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.warning(f"Failed to send message: {response.status}")
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.warning(f"Error sending message (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))
        
        return None
    
    async def broadcast_message(self, nodes: list, message: Message) -> Dict[str, Any]:
        """Broadcast a message to multiple nodes."""
        tasks = []
        for node in nodes:
            if node['id'] != self.node_id:
                task = self.send_message(node['host'], node['port'], message)
                tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        responses = {}
        for i, node in enumerate([n for n in nodes if n['id'] != self.node_id]):
            if i < len(results) and not isinstance(results[i], Exception):
                responses[node['id']] = results[i]
        
        return responses
    
    async def _handle_message(self, request: web.Request) -> web.Response:
        """Handle incoming messages."""
        try:
            data = await request.json()
            message = Message.from_dict(data)
            
            handler = self.handlers.get(message.msg_type)
            if handler:
                response = await handler(message)
                return web.json_response(response if response else {})
            else:
                logger.warning(f"No handler registered for message type: {message.msg_type}")
                return web.json_response({'error': 'No handler found'}, status=404)
        
        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
            return web.json_response({'error': str(e)}, status=500)
    
    async def _handle_health(self, request: web.Request) -> web.Response:
        """Handle health check requests."""
        return web.json_response({
            'status': 'healthy',
            'node_id': self.node_id,
            'timestamp': time.time()
        })


class RPCClient:
    """RPC client for making remote procedure calls."""
    
    def __init__(self, message_passing: MessagePassing):
        self.message_passing = message_passing
        self.pending_requests: Dict[str, asyncio.Future] = {}
    
    async def call(self, target_host: str, target_port: int, 
                   method: str, params: Dict[str, Any], timeout: float = 5.0) -> Any:
        """Make an RPC call to a remote node."""
        message = Message(
            msg_type=MessageType.PING,
            sender_id=self.message_passing.node_id,
            receiver_id="",
            payload={
                'method': method,
                'params': params
            }
        )
        
        try:
            response = await asyncio.wait_for(
                self.message_passing.send_message(target_host, target_port, message),
                timeout=timeout
            )
            return response
        except asyncio.TimeoutError:
            logger.error(f"RPC call to {target_host}:{target_port} timed out")
            return None
