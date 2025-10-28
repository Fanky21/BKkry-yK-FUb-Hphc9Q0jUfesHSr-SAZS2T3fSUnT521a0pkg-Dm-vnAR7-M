"""Unit tests for Queue Node."""

import pytest
from src.nodes.queue_node import QueueNode, ConsistentHash, QueueMessage
from src.utils.config import Config


@pytest.fixture
def config():
    """Create test configuration."""
    cfg = Config()
    cfg.node_id = 'test-node'
    cfg.node_host = 'localhost'
    cfg.node_port = 5000
    cfg.cluster_nodes = []
    cfg.queue_persist_dir = './test_data/queue'
    return cfg


def test_consistent_hash():
    """Test consistent hashing."""
    nodes = ['node-1', 'node-2', 'node-3']
    ring = ConsistentHash(nodes)
    
    node = ring.get_node('test-key')
    assert node in nodes
    
    node2 = ring.get_node('test-key')
    assert node == node2


def test_consistent_hash_add_remove():
    """Test adding and removing nodes from hash ring."""
    nodes = ['node-1', 'node-2']
    ring = ConsistentHash(nodes)
    
    ring.add_node('node-3')
    assert 'node-3' in ring.nodes
    
    ring.remove_node('node-2')
    assert 'node-2' not in ring.nodes


def test_consistent_hash_replicas():
    """Test getting replica nodes."""
    nodes = ['node-1', 'node-2', 'node-3', 'node-4']
    ring = ConsistentHash(nodes)
    
    replicas = ring.get_replicas('test-key', count=3)
    
    assert len(replicas) == 3
    assert len(set(replicas)) == 3


def test_queue_message():
    """Test queue message creation."""
    msg = QueueMessage(
        message_id='test-1',
        payload={'data': 'test'},
        max_retries=3
    )
    
    assert msg.message_id == 'test-1'
    assert msg.payload['data'] == 'test'
    assert msg.retries == 0
    assert msg.max_retries == 3
    
    msg_dict = msg.to_dict()
    assert msg_dict['message_id'] == 'test-1'
    assert msg_dict['payload']['data'] == 'test'
