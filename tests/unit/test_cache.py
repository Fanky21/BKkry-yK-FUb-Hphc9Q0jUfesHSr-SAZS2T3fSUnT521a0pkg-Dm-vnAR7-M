"""Unit tests for Cache Node."""

import pytest
from src.nodes.cache_node import CacheNode, CacheState, LRUCache, CacheEntry
from src.utils.config import Config


@pytest.fixture
def config():
    """Create test configuration."""
    cfg = Config()
    cfg.node_id = 'test-node'
    cfg.node_host = 'localhost'
    cfg.node_port = 5000
    cfg.cluster_nodes = []
    cfg.cache_size = 10
    return cfg


def test_cache_states():
    """Test cache state enumeration."""
    assert CacheState.MODIFIED.value == "M"
    assert CacheState.EXCLUSIVE.value == "E"
    assert CacheState.SHARED.value == "S"
    assert CacheState.INVALID.value == "I"


def test_lru_cache_basic():
    """Test basic LRU cache operations."""
    cache = LRUCache(capacity=3)
    
    cache.put('key1', 'value1')
    cache.put('key2', 'value2')
    cache.put('key3', 'value3')
    
    assert cache.size() == 3
    
    entry = cache.get('key1')
    assert entry is not None
    assert entry.value == 'value1'


def test_lru_cache_eviction():
    """Test LRU eviction."""
    cache = LRUCache(capacity=2)
    
    cache.put('key1', 'value1')
    cache.put('key2', 'value2')
    cache.put('key3', 'value3')
    
    assert cache.size() == 2
    assert cache.get('key1') is None
    assert cache.get('key2') is not None
    assert cache.get('key3') is not None


def test_lru_cache_update():
    """Test updating existing entries."""
    cache = LRUCache(capacity=3)
    
    cache.put('key1', 'value1')
    cache.put('key1', 'value2')
    
    entry = cache.get('key1')
    assert entry.value == 'value2'
    assert cache.size() == 1


def test_cache_entry():
    """Test cache entry creation."""
    entry = CacheEntry(
        key='test',
        value='data',
        state=CacheState.EXCLUSIVE
    )
    
    assert entry.key == 'test'
    assert entry.value == 'data'
    assert entry.state == CacheState.EXCLUSIVE
    assert entry.access_count == 0


def test_cache_invalidation():
    """Test cache invalidation."""
    cache = LRUCache(capacity=5)
    
    cache.put('key1', 'value1', CacheState.EXCLUSIVE)
    cache.invalidate('key1')
    
    entry = cache.get('key1')
    assert entry.state == CacheState.INVALID
