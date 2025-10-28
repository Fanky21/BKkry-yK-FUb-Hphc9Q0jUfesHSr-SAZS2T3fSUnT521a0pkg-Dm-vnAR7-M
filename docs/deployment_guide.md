# Deployment Guide

## Prerequisites

### System Requirements

- **Operating System**: Linux (Ubuntu 20.04+), macOS, or Windows with WSL2
- **CPU**: Minimum 2 cores, Recommended 4+ cores
- **RAM**: Minimum 4GB, Recommended 8GB+
- **Disk**: Minimum 10GB free space
- **Network**: Stable network connection with low latency between nodes

### Software Requirements

- **Docker**: Version 20.10+
- **Docker Compose**: Version 2.0+
- **Python**: Version 3.11+ (for development)
- **Git**: For cloning repository

## Installation Methods

### Method 1: Docker Compose (Recommended)

This is the easiest method for deploying the entire cluster.

#### Step 1: Clone Repository

```bash
git clone <repository-url>
cd distributed-sync-system
```

#### Step 2: Configure Environment

```bash
cd docker
cp ../.env.example .env

# Edit .env file with your configuration
nano .env
```

#### Step 3: Build and Start

```bash
# Build images
docker-compose build

# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

#### Step 4: Verify Deployment

```bash
# Check node 1
curl http://localhost:5000/health

# Check node 2
curl http://localhost:5001/health

# Check node 3
curl http://localhost:5002/health

# Check Prometheus
curl http://localhost:9090

# Access Grafana
# Open browser: http://localhost:3000
# Login: admin/admin
```

### Method 2: Manual Deployment

For more control over the deployment process.

#### Step 1: Setup Python Environment

```bash
# Create virtual environment
python -m venv venv

# Activate (Linux/Mac)
source venv/bin/activate

# Activate (Windows)
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

#### Step 2: Setup Redis

```bash
# Using Docker
docker run -d \
  --name redis \
  -p 6379:6379 \
  redis:7-alpine

# Or install Redis natively
sudo apt-get install redis-server
redis-server
```

#### Step 3: Start Nodes

Open three terminal windows:

**Terminal 1 - Node 1:**
```bash
export NODE_ID=node-1
export NODE_HOST=0.0.0.0
export NODE_PORT=5000
export CLUSTER_NODES=localhost:5001,localhost:5002
export REDIS_HOST=localhost
export LOG_LEVEL=INFO

python -m src.main
```

**Terminal 2 - Node 2:**
```bash
export NODE_ID=node-2
export NODE_HOST=0.0.0.0
export NODE_PORT=5001
export CLUSTER_NODES=localhost:5000,localhost:5002
export REDIS_HOST=localhost
export LOG_LEVEL=INFO

python -m src.main
```

**Terminal 3 - Node 3:**
```bash
export NODE_ID=node-3
export NODE_HOST=0.0.0.0
export NODE_PORT=5002
export CLUSTER_NODES=localhost:5000,localhost:5001
export REDIS_HOST=localhost
export LOG_LEVEL=INFO

python -m src.main
```

## Production Deployment

### AWS Deployment

#### Using EC2 Instances

1. **Launch EC2 Instances**
   - Launch 3 t3.medium instances (Ubuntu 22.04)
   - Configure security group to allow ports: 5000, 6379, 9090
   - Assign Elastic IPs for static addressing

2. **Install Docker on Each Instance**

```bash
# Update system
sudo apt-get update
sudo apt-get upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

3. **Deploy Application**

```bash
# Clone repository
git clone <repository-url>
cd distributed-sync-system/docker

# Update docker-compose.yml with actual IPs
# Edit CLUSTER_NODES to use EC2 private IPs

# Start services
docker-compose up -d
```

#### Using ECS (Elastic Container Service)

1. Create ECR repositories for Docker images
2. Build and push images to ECR
3. Create ECS task definitions
4. Configure ECS service with 3 tasks
5. Setup Application Load Balancer
6. Configure CloudWatch for monitoring

### Kubernetes Deployment

#### Create Kubernetes Manifests

**1. ConfigMap (distributed-config.yaml):**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: distributed-config
data:
  REDIS_HOST: "redis-service"
  REDIS_PORT: "6379"
  LOG_LEVEL: "INFO"
  CACHE_SIZE: "1000"
```

**2. StatefulSet (distributed-nodes.yaml):**

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: distributed-node
spec:
  serviceName: "distributed-node"
  replicas: 3
  selector:
    matchLabels:
      app: distributed-node
  template:
    metadata:
      labels:
        app: distributed-node
    spec:
      containers:
      - name: node
        image: your-registry/distributed-node:latest
        ports:
        - containerPort: 5000
          name: node-port
        envFrom:
        - configMapRef:
            name: distributed-config
        env:
        - name: NODE_ID
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        - name: NODE_PORT
          value: "5000"
        volumeMounts:
        - name: data
          mountPath: /app/data
  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: [ "ReadWriteOnce" ]
      resources:
        requests:
          storage: 10Gi
```

**3. Deploy:**

```bash
# Create namespace
kubectl create namespace distributed-system

# Apply manifests
kubectl apply -f distributed-config.yaml -n distributed-system
kubectl apply -f redis-deployment.yaml -n distributed-system
kubectl apply -f distributed-nodes.yaml -n distributed-system

# Verify deployment
kubectl get pods -n distributed-system
kubectl logs -f distributed-node-0 -n distributed-system
```

## Monitoring Setup

### Prometheus

1. **Configure Prometheus**

Edit `docker/prometheus.yml`:

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'distributed-nodes'
    static_configs:
      - targets: 
          - 'node-1:9090'
          - 'node-2:9090'
          - 'node-3:9090'
```

2. **Access Prometheus**
   - URL: http://localhost:9090
   - Query examples:
     - `rate(locks_acquired[5m])`
     - `cache_hit_rate`
     - `messages_enqueued_total`

### Grafana

1. **Access Grafana**
   - URL: http://localhost:3000
   - Default credentials: admin/admin

2. **Add Prometheus Data Source**
   - Configuration > Data Sources > Add data source
   - Select Prometheus
   - URL: http://prometheus:9090
   - Save & Test

3. **Import Dashboards**
   - Create new dashboard
   - Add panels for:
     - Node health
     - Lock statistics
     - Queue throughput
     - Cache hit rates

## Scaling

### Horizontal Scaling

#### Add New Node

1. **Update Configuration**

Add new node to `CLUSTER_NODES` in existing nodes.

2. **Start New Node**

```bash
docker run -d \
  --name node-4 \
  --network distributed-net \
  -e NODE_ID=node-4 \
  -e NODE_PORT=5000 \
  -e CLUSTER_NODES=node-1:5000,node-2:5000,node-3:5000 \
  -e REDIS_HOST=redis \
  -p 5003:5000 \
  distributed-node:latest
```

3. **Verify Integration**

```bash
curl http://localhost:5003/health
curl http://localhost:5003/api/status
```

### Vertical Scaling

Increase resources for existing nodes:

```yaml
# docker-compose.yml
services:
  node-1:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G
```

## Backup and Recovery

### Backup

1. **Backup Persistent Data**

```bash
# Backup queue data
docker exec node-1 tar czf /tmp/queue-backup.tar.gz /app/data/queue

# Copy backup
docker cp node-1:/tmp/queue-backup.tar.gz ./backups/

# Backup Redis
docker exec redis redis-cli BGSAVE
docker cp redis:/data/dump.rdb ./backups/redis-dump.rdb
```

2. **Automated Backup Script**

```bash
#!/bin/bash
BACKUP_DIR=/backups/$(date +%Y%m%d)
mkdir -p $BACKUP_DIR

# Backup all nodes
for i in 1 2 3; do
  docker cp node-$i:/app/data $BACKUP_DIR/node-$i
done

# Backup Redis
docker cp redis:/data/dump.rdb $BACKUP_DIR/

# Compress
tar czf $BACKUP_DIR.tar.gz $BACKUP_DIR
rm -rf $BACKUP_DIR
```

### Recovery

```bash
# Stop services
docker-compose down

# Restore data
tar xzf backups/20240101.tar.gz
docker cp backups/20240101/node-1 node-1:/app/data

# Start services
docker-compose up -d
```

## Troubleshooting

### Common Issues

#### 1. Nodes Can't Connect

**Symptoms:** Nodes show "suspected" or "dead" status

**Solutions:**
```bash
# Check network connectivity
docker exec node-1 ping node-2

# Check firewall rules
sudo ufw status

# Verify CLUSTER_NODES configuration
docker exec node-1 env | grep CLUSTER
```

#### 2. Raft Elections Failing

**Symptoms:** No leader elected, frequent elections

**Solutions:**
```bash
# Check election timeout configuration
# Increase timeouts in .env
ELECTION_TIMEOUT_MIN=3.0
ELECTION_TIMEOUT_MAX=5.0

# Check for clock skew
docker exec node-1 date
docker exec node-2 date

# Synchronize clocks if needed
sudo ntpdate -s time.nist.gov
```

#### 3. Memory Issues

**Symptoms:** Out of memory errors

**Solutions:**
```bash
# Check memory usage
docker stats

# Reduce cache size
CACHE_SIZE=500

# Increase container memory limit
docker update --memory 2g node-1
```

#### 4. Disk Full

**Symptoms:** Queue persistence fails

**Solutions:**
```bash
# Check disk usage
df -h

# Clean old queue data
docker exec node-1 find /app/data/queue -mtime +7 -delete

# Configure retention policy
QUEUE_RETENTION_DAYS=7
```

### Logs and Debugging

```bash
# View all logs
docker-compose logs -f

# View specific node
docker-compose logs -f node-1

# View last 100 lines
docker-compose logs --tail=100 node-1

# Enable debug logging
docker exec -it node-1 sh -c 'echo "LOG_LEVEL=DEBUG" >> /app/.env'
docker restart node-1

# Export logs
docker-compose logs > system-logs.txt
```

## Performance Tuning

### Network Optimization

```bash
# Increase TCP buffer sizes
echo 'net.core.rmem_max = 134217728' | sudo tee -a /etc/sysctl.conf
echo 'net.core.wmem_max = 134217728' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

### Redis Optimization

```bash
# Increase max connections
docker exec redis redis-cli CONFIG SET maxclients 10000

# Enable persistence
docker exec redis redis-cli CONFIG SET save "900 1 300 10"
```

### Application Tuning

Edit `.env`:
```bash
# Reduce heartbeat overhead
HEARTBEAT_INTERVAL=1.0

# Increase queue batch size
QUEUE_BATCH_SIZE=500

# Optimize cache size
CACHE_SIZE=5000
```

## Security

### Enable TLS

1. Generate certificates
2. Update Docker configuration
3. Configure nodes to use TLS

### Network Isolation

```bash
# Create isolated network
docker network create --driver bridge --subnet 172.20.0.0/16 distributed-secure

# Update docker-compose.yml to use custom network
```

### Access Control

Implement authentication and authorization (future feature).

## Health Checks

Setup automated health monitoring:

```bash
#!/bin/bash
# healthcheck.sh

for port in 5000 5001 5002; do
  response=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$port/health)
  if [ $response != "200" ]; then
    echo "Node on port $port is unhealthy"
    # Send alert
  fi
done
```

Add to cron:
```bash
*/5 * * * * /path/to/healthcheck.sh
```

## Support

For issues and questions:
- GitHub Issues: <repository-url>/issues
- Email: support@example.com
- Documentation: <repository-url>/docs
