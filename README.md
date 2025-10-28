Youtube: https://youtu.be/mzzJPRiXQqo

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Distributed System                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐             │
│  │  Node 1  │◄──►│  Node 2  │◄──►│  Node 3  │             │
│  ├──────────┤    ├──────────┤    ├──────────┤             │
│  │  Raft    │    │  Raft    │    │  Raft    │             │
│  │  Locks   │    │  Locks   │    │  Locks   │             │
│  │  Queue   │    │  Queue   │    │  Queue   │             │
│  │  Cache   │    │  Cache   │    │  Cache   │             │
│  └────┬─────┘    └────┬─────┘    └────┬─────┘             │
│       │               │               │                     │
│       └───────────────┼───────────────┘                     │
│                       │                                     │
│                  ┌────▼────┐                                │
│                  │  Redis  │ (Shared State)                 │
│                  └─────────┘                                │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Raft Consensus Flow

```
Follower → Election Timeout → Candidate
                                  ↓
                           Request Votes
                                  ↓
                          Majority Votes?
                                  ↓
                               Leader
                                  ↓
                           Send Heartbeats
                                  ↓
                          Replicate Logs
```

### MESI Cache States

```
Invalid (I) ──Read──► Shared (S) ──Write──► Modified (M)
                          │                       │
                          │                       │
Exclusive (E) ◄──Read─────┘                       │
      │                                           │
      └──────────────Write──────────────────────►┘
```

## Installation

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- Redis (included in Docker Compose)

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd distributed-sync-system
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment:
```bash
cp .env.example .env
# Edit .env with your configuration
```

## Running the System

### Using Docker Compose (Recommended)

```bash
# Start the entire cluster
cd docker
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the cluster
docker-compose down
```

This starts:
- 3 distributed nodes (ports 5000, 5001, 5002)
- Redis server (port 6379)
- Prometheus (port 9090)
- Grafana (port 3000)

### Running Individual Nodes

```bash
# Node 1
NODE_ID=node-1 NODE_PORT=5000 CLUSTER_NODES=localhost:5001,localhost:5002 python -m src.main

# Node 2
NODE_ID=node-2 NODE_PORT=5001 CLUSTER_NODES=localhost:5000,localhost:5002 python -m src.main

# Node 3
NODE_ID=node-3 NODE_PORT=5002 CLUSTER_NODES=localhost:5000,localhost:5001 python -m src.main
```

## Testing

### Unit Tests

```bash
# Run all unit tests
pytest tests/unit/ -v

# Run specific test file
pytest tests/unit/test_raft.py -v

# Run with coverage
pytest tests/unit/ --cov=src --cov-report=html
```

### Integration Tests

```bash
# Run integration tests
pytest tests/integration/ -v
```

### Performance Tests

```bash
# Run load tests with Locust
locust -f benchmarks/load_test_scenarios.py --host=http://localhost:5000
```

## Usage Examples

### Distributed Locks

```python
from src.nodes.lock_manager import LockManager, LockType

# Acquire exclusive lock
success = await lock_manager.acquire_lock(
    resource_id="resource-1",
    client_id="client-1",
    lock_type=LockType.EXCLUSIVE,
    timeout=30.0
)

# Release lock
await lock_manager.release_lock("resource-1", "client-1")
```

### Distributed Queue

```python
from src.nodes.queue_node import QueueNode

# Enqueue message
await queue_node.enqueue("my-queue", {"data": "hello"})

# Dequeue message
message = await queue_node.dequeue("my-queue", "consumer-1")

# Acknowledge message
await queue_node.acknowledge(message['message_id'])
```

### Distributed Cache

```python
from src.nodes.cache_node import CacheNode

# Put value in cache
await cache_node.put("key1", "value1")

# Get value from cache
value = await cache_node.get("key1")

# Invalidate cache entry
await cache_node.invalidate("key1")
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `NODE_ID` | Unique node identifier | `node-1` |
| `NODE_HOST` | Node host address | `0.0.0.0` |
| `NODE_PORT` | Node port | `5000` |
| `CLUSTER_NODES` | Comma-separated list of other nodes | `""` |
| `REDIS_HOST` | Redis host | `localhost` |
| `REDIS_PORT` | Redis port | `6379` |
| `CACHE_SIZE` | Maximum cache entries | `1000` |
| `CACHE_COHERENCE_PROTOCOL` | Cache protocol (MESI/MOSI/MOESI) | `MESI` |
| `LOG_LEVEL` | Logging level | `INFO` |

## Project Structure

```
distributed-sync-system/
├── src/
│   ├── nodes/              # Node implementations
│   ├── consensus/          # Raft consensus
│   ├── communication/      # Message passing
│   └── utils/              # Utilities
├── tests/
│   ├── unit/              # Unit tests
│   ├── integration/       # Integration tests
│   └── performance/       # Performance tests
├── docker/                # Docker configuration
├── docs/                  # Documentation
├── benchmarks/            # Load testing
└── requirements.txt       # Dependencies
```

## References

- [Raft Consensus Algorithm](https://raft.github.io/)
- [MESI Protocol](https://en.wikipedia.org/wiki/MESI_protocol)
- [Consistent Hashing](https://en.wikipedia.org/wiki/Consistent_hashing)
