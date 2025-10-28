"""Unit tests for Lock Manager."""

import pytest
import asyncio
from src.nodes.lock_manager import LockManager, LockType, DeadlockDetector
from src.utils.config import Config


@pytest.fixture
def config():
    """Create test configuration."""
    cfg = Config()
    cfg.node_id = 'test-node'
    cfg.node_host = 'localhost'
    cfg.node_port = 5000
    cfg.cluster_nodes = []
    return cfg


@pytest.mark.asyncio
async def test_lock_manager_initialization(config):
    """Test lock manager initialization."""
    lm = LockManager(config)
    
    assert lm.node_id == 'test-node'
    assert len(lm.locks) == 0
    assert len(lm.client_locks) == 0


def test_deadlock_detector():
    """Test deadlock detection."""
    detector = DeadlockDetector()
    
    detector.add_wait('A', 'B')
    detector.add_wait('B', 'C')
    detector.add_wait('C', 'A')
    
    cycle = detector.detect_deadlock()
    
    assert cycle is not None
    assert 'A' in cycle
    assert 'B' in cycle
    assert 'C' in cycle


def test_deadlock_detector_no_cycle():
    """Test deadlock detection with no cycle."""
    detector = DeadlockDetector()
    
    detector.add_wait('A', 'B')
    detector.add_wait('B', 'C')
    
    cycle = detector.detect_deadlock()
    
    assert cycle is None


def test_lock_types():
    """Test lock type enumeration."""
    assert LockType.SHARED.value == "shared"
    assert LockType.EXCLUSIVE.value == "exclusive"
