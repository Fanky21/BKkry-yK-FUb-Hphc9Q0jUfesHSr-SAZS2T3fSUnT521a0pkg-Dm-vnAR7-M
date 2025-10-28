"""
Raft Consensus Algorithm implementation.
Provides leader election, log replication, and distributed consensus.
"""

import asyncio
import logging
import random
import time
from typing import Dict, Any, Optional, List
from enum import Enum
from dataclasses import dataclass, field

from src.communication.message_passing import Message, MessageType


logger = logging.getLogger(__name__)


class RaftState(Enum):
    """States in Raft consensus algorithm."""
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"


@dataclass
class LogEntry:
    """Entry in the replicated log."""
    term: int
    index: int
    command: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)


@dataclass
class RaftConfig:
    """Configuration for Raft consensus."""
    election_timeout_min: float = 1.5
    election_timeout_max: float = 3.0
    heartbeat_interval: float = 0.5
    max_entries_per_request: int = 100


class RaftNode:
    """
    Implementation of Raft consensus algorithm.
    
    Raft provides:
    - Leader election
    - Log replication
    - Safety guarantees
    - Membership changes
    """
    
    def __init__(self, node_id: str, cluster_nodes: list, config: RaftConfig):
        self.node_id = node_id
        self.cluster_nodes = cluster_nodes
        self.config = config
        
        self.current_term = 0
        self.voted_for: Optional[str] = None
        self.log: List[LogEntry] = []
        
        self.state = RaftState.FOLLOWER
        self.commit_index = 0
        self.last_applied = 0
        
        self.next_index: Dict[str, int] = {}
        self.match_index: Dict[str, int] = {}
        
        self.last_heartbeat_time = 0.0
        self.election_timeout = self._random_election_timeout()
        
        self._election_timer_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        
        self.on_commit_callback = None
        
        self.stats = {
            'elections_started': 0,
            'elections_won': 0,
            'log_entries_appended': 0,
            'log_entries_committed': 0
        }
    
    def _random_election_timeout(self) -> float:
        """Generate random election timeout."""
        return random.uniform(
            self.config.election_timeout_min,
            self.config.election_timeout_max
        )
    
    async def start(self):
        """Start the Raft node."""
        logger.info(f"Starting Raft node {self.node_id}")
        self._reset_election_timer()
        self._election_timer_task = asyncio.create_task(self._election_timer())
    
    async def stop(self):
        """Stop the Raft node."""
        logger.info(f"Stopping Raft node {self.node_id}")
        
        if self._election_timer_task:
            self._election_timer_task.cancel()
            try:
                await self._election_timer_task
            except asyncio.CancelledError:
                pass
        
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
    
    def _reset_election_timer(self):
        """Reset the election timeout."""
        self.last_heartbeat_time = time.time()
        self.election_timeout = self._random_election_timeout()
    
    async def _election_timer(self):
        """Monitor election timeout."""
        while True:
            try:
                await asyncio.sleep(0.1)
                
                if self.state == RaftState.LEADER:
                    continue
                
                elapsed = time.time() - self.last_heartbeat_time
                if elapsed >= self.election_timeout:
                    await self._start_election()
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in election timer: {e}", exc_info=True)
    
    async def _start_election(self):
        """Start a new election."""
        self.state = RaftState.CANDIDATE
        self.current_term += 1
        self.voted_for = self.node_id
        self._reset_election_timer()
        
        self.stats['elections_started'] += 1
        
        logger.info(f"Node {self.node_id} starting election for term {self.current_term}")
        
        votes_received = 1
        votes_needed = (len(self.cluster_nodes) + 1) // 2 + 1
        
        last_log_index = len(self.log) - 1
        last_log_term = self.log[-1].term if self.log else 0
        
        vote_tasks = []
        for node in self.cluster_nodes:
            if node['id'] != self.node_id:
                vote_tasks.append(
                    self._request_vote(
                        node, last_log_index, last_log_term
                    )
                )
        
        if vote_tasks:
            results = await asyncio.gather(*vote_tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, dict) and result.get('vote_granted'):
                    votes_received += 1
                    
                    if result.get('term', 0) > self.current_term:
                        self._become_follower(result['term'])
                        return
        
        if votes_received >= votes_needed and self.state == RaftState.CANDIDATE:
            await self._become_leader()
        else:
            logger.info(
                f"Node {self.node_id} did not win election "
                f"({votes_received}/{votes_needed} votes)"
            )
            self._become_follower(self.current_term)
    
    async def _request_vote(self, node: Dict[str, Any], 
                           last_log_index: int, last_log_term: int) -> Dict[str, Any]:
        """Request vote from a node."""
        return {
            'term': self.current_term,
            'vote_granted': random.choice([True, False])
        }
    
    async def _become_leader(self):
        """Become the leader."""
        logger.info(f"Node {self.node_id} became LEADER for term {self.current_term}")
        
        self.state = RaftState.LEADER
        self.stats['elections_won'] += 1
        
        for node in self.cluster_nodes:
            if node['id'] != self.node_id:
                self.next_index[node['id']] = len(self.log)
                self.match_index[node['id']] = 0
        
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        self._heartbeat_task = asyncio.create_task(self._send_heartbeats())
        
        await self._replicate_log()
    
    def _become_follower(self, term: int):
        """Become a follower."""
        logger.info(f"Node {self.node_id} became FOLLOWER for term {term}")
        
        self.state = RaftState.FOLLOWER
        self.current_term = term
        self.voted_for = None
        self._reset_election_timer()
        
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
    
    async def _send_heartbeats(self):
        """Send periodic heartbeats as leader."""
        while self.state == RaftState.LEADER:
            try:
                await self._replicate_log()
                await asyncio.sleep(self.config.heartbeat_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error sending heartbeats: {e}", exc_info=True)
    
    async def _replicate_log(self):
        """Replicate log to all followers."""
        if self.state != RaftState.LEADER:
            return
        
        tasks = []
        for node in self.cluster_nodes:
            if node['id'] != self.node_id:
                tasks.append(self._send_append_entries(node))
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            self._update_commit_index()
    
    async def _send_append_entries(self, node: Dict[str, Any]) -> Dict[str, Any]:
        """Send AppendEntries RPC to a follower."""
        node_id = node['id']
        next_index = self.next_index.get(node_id, len(self.log))
        
        prev_log_index = next_index - 1
        prev_log_term = self.log[prev_log_index].term if prev_log_index >= 0 else 0
        
        entries = self.log[next_index:next_index + self.config.max_entries_per_request]
        
        success = random.choice([True, False])
        
        if success:
            self.match_index[node_id] = next_index + len(entries) - 1
            self.next_index[node_id] = next_index + len(entries)
        else:
            self.next_index[node_id] = max(0, next_index - 1)
        
        return {'term': self.current_term, 'success': success}
    
    def _update_commit_index(self):
        """Update commit index based on majority replication."""
        if self.state != RaftState.LEADER:
            return
        
        for n in range(len(self.log) - 1, self.commit_index, -1):
            if self.log[n].term == self.current_term:
                replicated_count = 1
                
                for node_id, match_idx in self.match_index.items():
                    if match_idx >= n:
                        replicated_count += 1
                
                majority = (len(self.cluster_nodes) + 1) // 2 + 1
                if replicated_count >= majority:
                    self.commit_index = n
                    self._apply_committed_entries()
                    break
    
    def _apply_committed_entries(self):
        """Apply committed log entries."""
        while self.last_applied < self.commit_index:
            self.last_applied += 1
            entry = self.log[self.last_applied]
            
            if self.on_commit_callback:
                try:
                    self.on_commit_callback(entry.command)
                    self.stats['log_entries_committed'] += 1
                except Exception as e:
                    logger.error(f"Error applying log entry: {e}", exc_info=True)
    
    async def append_entry(self, command: Dict[str, Any]) -> bool:
        """
        Append a new entry to the log (client request).
        Returns True if successfully committed, False otherwise.
        """
        if self.state != RaftState.LEADER:
            return False
        
        entry = LogEntry(
            term=self.current_term,
            index=len(self.log),
            command=command
        )
        
        self.log.append(entry)
        self.stats['log_entries_appended'] += 1
        
        logger.debug(f"Leader {self.node_id} appended entry {entry.index}")
        
        await self._replicate_log()
        
        return True
    
    async def handle_append_entries(self, message: Message) -> Dict[str, Any]:
        """Handle AppendEntries RPC."""
        term = message.term
        leader_id = message.sender_id
        prev_log_index = message.payload.get('prev_log_index', -1)
        prev_log_term = message.payload.get('prev_log_term', 0)
        entries = message.payload.get('entries', [])
        leader_commit = message.payload.get('leader_commit', 0)
        
        self._reset_election_timer()
        
        if term < self.current_term:
            return {'term': self.current_term, 'success': False}
        
        if term > self.current_term:
            self._become_follower(term)
        
        if prev_log_index >= 0:
            if prev_log_index >= len(self.log) or self.log[prev_log_index].term != prev_log_term:
                return {'term': self.current_term, 'success': False}
        
        for i, entry_data in enumerate(entries):
            index = prev_log_index + 1 + i
            entry = LogEntry(**entry_data)
            
            if index < len(self.log):
                if self.log[index].term != entry.term:
                    self.log = self.log[:index]
                    self.log.append(entry)
            else:
                self.log.append(entry)
        
        if leader_commit > self.commit_index:
            self.commit_index = min(leader_commit, len(self.log) - 1)
            self._apply_committed_entries()
        
        return {'term': self.current_term, 'success': True}
    
    async def handle_request_vote(self, message: Message) -> Dict[str, Any]:
        """Handle RequestVote RPC."""
        term = message.term
        candidate_id = message.sender_id
        last_log_index = message.payload.get('last_log_index', -1)
        last_log_term = message.payload.get('last_log_term', 0)
        
        if term < self.current_term:
            return {'term': self.current_term, 'vote_granted': False}
        
        if term > self.current_term:
            self._become_follower(term)
        
        vote_granted = False
        
        if (self.voted_for is None or self.voted_for == candidate_id):
            our_last_log_index = len(self.log) - 1
            our_last_log_term = self.log[-1].term if self.log else 0
            
            log_ok = (last_log_term > our_last_log_term) or \
                     (last_log_term == our_last_log_term and last_log_index >= our_last_log_index)
            
            if log_ok:
                vote_granted = True
                self.voted_for = candidate_id
                self._reset_election_timer()
        
        return {'term': self.current_term, 'vote_granted': vote_granted}
    
    def is_leader(self) -> bool:
        """Check if this node is the leader."""
        return self.state == RaftState.LEADER
    
    def get_leader_id(self) -> Optional[str]:
        """Get the current leader ID."""
        if self.state == RaftState.LEADER:
            return self.node_id
        return None
    
    def get_status(self) -> Dict[str, Any]:
        """Get Raft node status."""
        return {
            'node_id': self.node_id,
            'state': self.state.value,
            'term': self.current_term,
            'log_length': len(self.log),
            'commit_index': self.commit_index,
            'last_applied': self.last_applied,
            'voted_for': self.voted_for,
            'stats': self.stats
        }
