"""Main entry point for distributed node."""

import asyncio
import logging
import sys
import signal
from typing import Optional

from src.utils.config import Config
from src.nodes.lock_manager import LockManager
from src.nodes.queue_node import QueueNode
from src.nodes.cache_node import CacheNode


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('node.log')
    ]
)

logger = logging.getLogger(__name__)


class DistributedNode:
    """Main distributed node that combines all components."""
    
    def __init__(self, config: Config):
        self.config = config
        self.lock_manager: Optional[LockManager] = None
        self.queue_node: Optional[QueueNode] = None
        self.cache_node: Optional[CacheNode] = None
        self.running = False
    
    async def start(self):
        """Start all node components."""
        logger.info("Starting distributed node...")
        
        self.lock_manager = LockManager(self.config)
        self.queue_node = QueueNode(self.config)
        self.cache_node = CacheNode(self.config)
        
        await self.lock_manager.start()
        await self.queue_node.start()
        await self.cache_node.start()
        
        self.running = True
        logger.info(f"Distributed node {self.config.node_id} started successfully")
    
    async def stop(self):
        """Stop all node components."""
        logger.info("Stopping distributed node...")
        
        self.running = False
        
        if self.cache_node:
            await self.cache_node.stop()
        
        if self.queue_node:
            await self.queue_node.stop()
        
        if self.lock_manager:
            await self.lock_manager.stop()
        
        logger.info("Distributed node stopped")
    
    def get_status(self) -> dict:
        """Get overall node status."""
        return {
            'node_id': self.config.node_id,
            'running': self.running,
            'lock_manager': self.lock_manager.get_status() if self.lock_manager else None,
            'queue': self.queue_node.get_status() if self.queue_node else None,
            'cache': self.cache_node.get_status() if self.cache_node else None
        }


async def main():
    """Main function."""
    config = Config.from_env()
    
    logging.getLogger().setLevel(config.log_level)
    
    node = DistributedNode(config)
    
    def signal_handler(sig, frame):
        logger.info("Received shutdown signal")
        asyncio.create_task(node.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await node.start()
        
        while node.running:
            await asyncio.sleep(1)
            
            if int(asyncio.get_event_loop().time()) % 60 == 0:
                status = node.get_status()
                logger.info(f"Node status: {status}")
    
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    
    except Exception as e:
        logger.error(f"Error in main loop: {e}", exc_info=True)
    
    finally:
        await node.stop()


if __name__ == '__main__':
    asyncio.run(main())
