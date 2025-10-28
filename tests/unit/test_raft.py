"""Unit tests for Raft consensus."""

import pytest
import asyncio
from src.consensus.raft import RaftNode, RaftState, RaftConfig, LogEntry


@pytest.fixture
def raft_config():
    """Create test Raft configuration."""
    return RaftConfig(
        election_timeout_min=0.5,
        election_timeout_max=1.0,
        heartbeat_interval=0.1
    )


@pytest.fixture
def cluster_nodes():
    """Create test cluster nodes."""
    return [
        {'id': 'node-2', 'host': 'localhost', 'port': 5001},
        {'id': 'node-3', 'host': 'localhost', 'port': 5002}
    ]


@pytest.mark.asyncio
async def test_raft_initialization(raft_config, cluster_nodes):
    """Test Raft node initialization."""
    node = RaftNode('node-1', cluster_nodes, raft_config)
    
    assert node.node_id == 'node-1'
    assert node.state == RaftState.FOLLOWER
    assert node.current_term == 0
    assert node.voted_for is None
    assert len(node.log) == 0


@pytest.mark.asyncio
async def test_raft_start_stop(raft_config, cluster_nodes):
    """Test starting and stopping Raft node."""
    node = RaftNode('node-1', cluster_nodes, raft_config)
    
    await node.start()
    assert node._election_timer_task is not None
    
    await node.stop()
    assert node._election_timer_task.cancelled() or node._election_timer_task.done()


@pytest.mark.asyncio
async def test_log_entry_creation():
    """Test creating log entries."""
    command = {'operation': 'set', 'key': 'test', 'value': 'data'}
    entry = LogEntry(term=1, index=0, command=command)
    
    assert entry.term == 1
    assert entry.index == 0
    assert entry.command == command


@pytest.mark.asyncio
async def test_append_entry(raft_config, cluster_nodes):
    """Test appending log entries."""
    node = RaftNode('node-1', cluster_nodes, raft_config)
    node.state = RaftState.LEADER
    node.current_term = 1
    
    command = {'operation': 'test'}
    result = await node.append_entry(command)
    
    assert result is True
    assert len(node.log) == 1
    assert node.log[0].command == command


def test_raft_status(raft_config, cluster_nodes):
    """Test getting Raft status."""
    node = RaftNode('node-1', cluster_nodes, raft_config)
    
    status = node.get_status()
    
    assert status['node_id'] == 'node-1'
    assert status['state'] == RaftState.FOLLOWER.value
    assert status['term'] == 0
    assert status['log_length'] == 0
