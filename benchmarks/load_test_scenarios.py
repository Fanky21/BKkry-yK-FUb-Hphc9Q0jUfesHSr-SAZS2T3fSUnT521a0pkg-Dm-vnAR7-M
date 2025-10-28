from locust import HttpUser, task, between, events
import random
import json


class DistributedSystemUser(HttpUser):
    """Simulated user for load testing."""
    
    wait_time = between(0.1, 1.0)
    
    def on_start(self):
        """Called when a user starts."""
        self.client_id = f"client-{random.randint(1, 10000)}"
    
    @task(3)
    def acquire_lock(self):
        """Test lock acquisition."""
        resource_id = f"resource-{random.randint(1, 100)}"
        
        response = self.client.post("/api/lock/acquire", json={
            "resource_id": resource_id,
            "client_id": self.client_id,
            "lock_type": random.choice(["shared", "exclusive"]),
            "timeout": 30.0
        })
        
        if response.status_code == 200:
            self.client.post("/api/lock/release", json={
                "resource_id": resource_id,
                "client_id": self.client_id
            })
    
    @task(5)
    def enqueue_message(self):
        """Test message enqueueing."""
        queue_name = f"queue-{random.randint(1, 10)}"
        
        self.client.post("/api/queue/enqueue", json={
            "queue_name": queue_name,
            "message": {
                "data": f"test-message-{random.randint(1, 1000)}",
                "timestamp": random.random()
            }
        })
    
    @task(4)
    def dequeue_message(self):
        """Test message dequeueing."""
        queue_name = f"queue-{random.randint(1, 10)}"
        
        response = self.client.post("/api/queue/dequeue", json={
            "queue_name": queue_name,
            "consumer_id": self.client_id
        })
        
        if response.status_code == 200 and response.json().get('message'):
            message_id = response.json()['message']['message_id']
            self.client.post("/api/queue/ack", json={
                "message_id": message_id
            })
    
    @task(6)
    def cache_operations(self):
        """Test cache get/put operations."""
        key = f"key-{random.randint(1, 1000)}"
        
        response = self.client.get(f"/api/cache/get/{key}")
        
        if response.status_code == 404:
            self.client.post("/api/cache/put", json={
                "key": key,
                "value": f"value-{random.random()}"
            })


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when test starts."""
    print("Starting load test...")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when test stops."""
    print("Load test completed.")
    print(f"Total requests: {environment.stats.total.num_requests}")
    print(f"Total failures: {environment.stats.total.num_failures}")
    print(f"Average response time: {environment.stats.total.avg_response_time:.2f}ms")


