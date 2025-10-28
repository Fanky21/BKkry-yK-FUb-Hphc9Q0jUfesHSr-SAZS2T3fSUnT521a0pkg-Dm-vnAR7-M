"""Configuration management for the distributed system."""

import os
from typing import Dict, Any
from dataclasses import dataclass, field


@dataclass
class Config:
    """Configuration class for distributed system."""
    
    node_id: str = field(default_factory=lambda: os.getenv('NODE_ID', 'node-1'))
    node_host: str = field(default_factory=lambda: os.getenv('NODE_HOST', 'localhost'))
    node_port: int = field(default_factory=lambda: int(os.getenv('NODE_PORT', '5000')))
    
    cluster_nodes: list = field(default_factory=list)
    
    election_timeout_min: float = 1.5
    election_timeout_max: float = 3.0
    heartbeat_interval: float = 0.5
    
    lock_timeout: float = 30.0
    deadlock_detection_interval: float = 5.0
    
    queue_persist_dir: str = field(default_factory=lambda: os.getenv('QUEUE_PERSIST_DIR', './data/queue'))
    queue_batch_size: int = 100
    queue_flush_interval: float = 1.0
    
    cache_size: int = 1000
    cache_coherence_protocol: str = 'MESI'
    cache_replacement_policy: str = 'LRU'
    
    request_timeout: float = 5.0
    max_retries: int = 3
    retry_delay: float = 0.5
    
    redis_host: str = field(default_factory=lambda: os.getenv('REDIS_HOST', 'localhost'))
    redis_port: int = field(default_factory=lambda: int(os.getenv('REDIS_PORT', '6379')))
    redis_db: int = field(default_factory=lambda: int(os.getenv('REDIS_DB', '0')))
    redis_password: str = field(default_factory=lambda: os.getenv('REDIS_PASSWORD', ''))
    
    metrics_enabled: bool = True
    metrics_port: int = 9090
    
    log_level: str = field(default_factory=lambda: os.getenv('LOG_LEVEL', 'INFO'))
    log_format: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    @classmethod
    def from_env(cls) -> 'Config':
        """Create configuration from environment variables."""
        config = cls()
        
        cluster_nodes_str = os.getenv('CLUSTER_NODES', '')
        if cluster_nodes_str:
            config.cluster_nodes = [
                {'host': node.split(':')[0], 'port': int(node.split(':')[1])}
                for node in cluster_nodes_str.split(',')
            ]
        
        return config
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            'node_id': self.node_id,
            'node_host': self.node_host,
            'node_port': self.node_port,
            'cluster_nodes': self.cluster_nodes,
            'election_timeout_min': self.election_timeout_min,
            'election_timeout_max': self.election_timeout_max,
            'heartbeat_interval': self.heartbeat_interval,
            'lock_timeout': self.lock_timeout,
            'deadlock_detection_interval': self.deadlock_detection_interval,
            'queue_persist_dir': self.queue_persist_dir,
            'queue_batch_size': self.queue_batch_size,
            'cache_size': self.cache_size,
            'cache_coherence_protocol': self.cache_coherence_protocol,
            'cache_replacement_policy': self.cache_replacement_policy,
            'redis_host': self.redis_host,
            'redis_port': self.redis_port,
            'metrics_enabled': self.metrics_enabled,
            'log_level': self.log_level
        }
