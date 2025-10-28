# System Architecture

## Overview

The Distributed Synchronization System is built on a peer-to-peer architecture where each node can act as a client or server. The system uses Raft consensus for coordination and provides distributed locks, queues, and cache coherence.

## Components

### 1. Base Node

The `BaseNode` class provides core functionality for all nodes:

- **Message Passing**: HTTP-based communication using aiohttp
- **Failure Detection**: Heartbeat-based failure detector
- **Metrics Collection**: Performance monitoring

### 2. Raft Consensus Layer

Implements the Raft consensus algorithm:

**States:**
- **Follower**: Default state, responds to RPCs
- **Candidate**: Requests votes during election
- **Leader**: Handles client requests and log replication

**Key Operations:**
- Leader election with randomized timeouts
- Log replication with consistency checks
- Commit index advancement based on majority

**Safety Properties:**
- Election Safety: At most one leader per term
- Leader Append-Only: Leader never deletes/overwrites entries
- Log Matching: If two logs contain entry with same index/term, all preceding entries are identical
- Leader Completeness: If entry committed in term, it appears in all future leader logs
- State Machine Safety: If server applies log entry at index, no other server applies different entry at that index

### 3. Lock Manager

Provides distributed locking with:

**Lock Types:**
- **Shared (Read) Locks**: Multiple readers allowed
- **Exclusive (Write) Locks**: Single writer, no readers

**Deadlock Detection:**
- Wait-for graph construction
- Cycle detection using DFS
- Deadlock resolution by aborting youngest transaction

**Consistency:**
- All lock operations go through Raft consensus
- Lock state replicated across majority of nodes

### 4. Queue System

Distributed message queue with:

**Consistent Hashing:**
- Virtual nodes for load distribution
- Automatic rebalancing on node add/remove
- Deterministic message placement

**Replication:**
- Messages replicated to 3 nodes (configurable)
- Automatic failover on node failure
- No message loss guarantee

**Delivery Semantics:**
- At-least-once delivery
- Message acknowledgments
- Automatic retry on timeout

### 5. Cache System

Distributed cache with MESI coherence:

**Cache States:**
- **Modified (M)**: Cache line dirty, exclusive owner
- **Exclusive (E)**: Cache line clean, exclusive owner
- **Shared (S)**: Cache line clean, may be shared
- **Invalid (I)**: Cache line not valid

**State Transitions:**
```
Read Hit (S/E/M) → Same state, access count++
Read Miss → Fetch from other nodes → S
Write Hit (E/M) → M
Write Hit (S) → Invalidate others → M
Write Miss → Invalidate others, fetch → M
```

**Coherence Protocol:**
1. Read: Check local cache → If miss, fetch from others
2. Write: Invalidate all other copies → Update local → Mark as Modified
3. Invalidation: Received invalidation → Mark local as Invalid

## Communication Protocol

### Message Types

1. **Raft Messages:**
   - `REQUEST_VOTE`: Candidate requests vote
   - `VOTE_RESPONSE`: Vote grant/deny response
   - `APPEND_ENTRIES`: Leader replicates log entries
   - `APPEND_ENTRIES_RESPONSE`: Follower acknowledges

2. **Lock Messages:**
   - `LOCK_REQUEST`: Request lock acquisition
   - `LOCK_RESPONSE`: Lock grant/deny response
   - `LOCK_RELEASE`: Release lock
   - `DEADLOCK_DETECTION`: Deadlock check

3. **Queue Messages:**
   - `ENQUEUE`: Add message to queue
   - `DEQUEUE`: Remove message from queue
   - `QUEUE_ACK`: Acknowledge message receipt

4. **Cache Messages:**
   - `CACHE_GET`: Read from cache
   - `CACHE_PUT`: Write to cache
   - `CACHE_INVALIDATE`: Invalidate cache line
   - `CACHE_UPDATE`: Directory update

### Message Format

```json
{
  "msg_type": "REQUEST_VOTE",
  "sender_id": "node-1",
  "receiver_id": "node-2",
  "term": 5,
  "payload": {
    "last_log_index": 10,
    "last_log_term": 4
  },
  "timestamp": 1234567890.123,
  "message_id": "unique-id"
}
```

## Failure Handling

### Node Failure

1. **Detection**: Heartbeat timeout triggers suspected state
2. **Consensus**: Raft automatically elects new leader
3. **Lock Recovery**: Locks held by failed node eventually timeout
4. **Queue Recovery**: Messages replicated on other nodes
5. **Cache Recovery**: Cache entries marked invalid, re-fetch on access

### Network Partition

1. **Split Brain Prevention**: Raft requires majority for operations
2. **Partition Detection**: Failure detector marks nodes as suspected/dead
3. **Partition Healing**: Nodes rejoin, logs reconciled, state synchronized

### Byzantine Faults

Current implementation assumes crash-fault model (no Byzantine faults). For Byzantine fault tolerance, implement PBFT (bonus feature).

## Scalability

### Horizontal Scaling

- Add nodes to increase capacity
- Consistent hashing automatically redistributes load
- Raft cluster can be expanded (requires reconfiguration)

### Performance Optimization

1. **Batching**: Combine multiple operations
2. **Pipelining**: Send multiple requests without waiting
3. **Caching**: Reduce remote reads
4. **Sharding**: Partition data across nodes

## Data Flow Examples

### Lock Acquisition Flow

```
Client → Node 1 (Follower)
         ↓
Node 1 → Node 2 (Leader): LOCK_REQUEST
         ↓
Node 2 → Raft: Append log entry
         ↓
Node 2 → All nodes: APPEND_ENTRIES
         ↓
Majority acknowledge
         ↓
Node 2: Commit entry, grant lock
         ↓
Node 2 → Node 1: LOCK_RESPONSE (granted)
         ↓
Node 1 → Client: Success
```

### Cache Read Flow

```
Client → Node 1: GET key1
         ↓
Node 1: Check local cache
         ↓
Cache miss
         ↓
Node 1 → Other nodes: CACHE_GET (probe)
         ↓
Node 2 has key1 (state: E)
         ↓
Node 2: Transition E → S
         ↓
Node 2 → Node 1: value1, state=S
         ↓
Node 1: Store locally (state: S)
         ↓
Node 1 → Client: value1
```

## Consistency Model

### Lock Manager
- **Strong Consistency**: All operations linearizable through Raft

### Queue System
- **Eventual Consistency**: Messages eventually delivered to all replicas
- **At-least-once**: Messages may be delivered multiple times

### Cache System
- **Sequential Consistency**: Cache operations appear in some sequential order
- **Cache Coherence**: All nodes eventually see same value for a key

## Security Considerations

### Current Implementation
- No authentication (trust all nodes)
- No encryption (plaintext communication)
- No authorization (all clients have full access)

### Production Requirements
- mTLS for inter-node communication
- JWT/OAuth for client authentication
- RBAC for authorization
- Audit logging for compliance

## Monitoring and Observability

### Metrics
- Node health (CPU, memory, network)
- Raft metrics (term, log size, commit index)
- Lock metrics (acquisitions, deadlocks, timeouts)
- Queue metrics (enqueue rate, dequeue rate, backlog)
- Cache metrics (hit rate, evictions, coherence messages)

### Logging
- Structured JSON logs
- Log levels: DEBUG, INFO, WARNING, ERROR
- Distributed tracing with correlation IDs

### Alerting
- Node down/unreachable
- Raft leader election failed
- Deadlock detected
- Queue backlog threshold exceeded
- Cache hit rate below threshold
