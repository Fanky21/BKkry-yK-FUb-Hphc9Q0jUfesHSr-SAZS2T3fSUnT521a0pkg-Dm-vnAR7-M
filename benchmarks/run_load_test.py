"""
Standalone Load Test Runner
Menjalankan load test tanpa menggunakan Locust
"""

import asyncio
import aiohttp
import time
import random
from statistics import mean, median

BASE_URLS = [
    "http://localhost:15000",
    "http://localhost:15001",
    "http://localhost:15002"
]

async def test_lock_operations(num_requests=100):
    """Test operasi lock"""
    print("\n=== Testing Lock Operations ===")
    
    results = []
    async with aiohttp.ClientSession() as session:
        for i in range(num_requests):
            resource_id = f"resource_{random.randint(1, 20)}"
            client_id = f"client_{i}"
            node_url = random.choice(BASE_URLS)
            
            start = time.time()
            try:
                async with session.post(
                    f"{node_url}/lock/acquire",
                    json={
                        "resource_id": resource_id,
                        "client_id": client_id,
                        "lock_type": "exclusive"
                    },
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    await resp.json()
                    duration = time.time() - start
                    results.append({
                        "success": resp.status == 200,
                        "duration": duration
                    })
                    
                    if resp.status == 200:
                        await session.post(
                            f"{node_url}/lock/release",
                            json={
                                "resource_id": resource_id,
                                "client_id": client_id
                            }
                        )
            except Exception as e:
                results.append({
                    "success": False,
                    "duration": time.time() - start,
                    "error": str(e)
                })
            
            if (i + 1) % 10 == 0:
                print(f"Progress: {i + 1}/{num_requests}")
    
    success_count = sum(1 for r in results if r["success"])
    durations = [r["duration"] for r in results if r["success"]]
    
    print(f"\n📊 Lock Test Results:")
    print(f"  Total requests: {num_requests}")
    print(f"  Successful: {success_count} ({success_count/num_requests*100:.1f}%)")
    print(f"  Failed: {num_requests - success_count}")
    if durations:
        print(f"  Avg response time: {mean(durations)*1000:.2f}ms")
        print(f"  Median response time: {median(durations)*1000:.2f}ms")
        print(f"  Min: {min(durations)*1000:.2f}ms, Max: {max(durations)*1000:.2f}ms")

async def test_queue_operations(num_requests=100):
    """Test operasi queue"""
    print("\n=== Testing Queue Operations ===")
    
    enqueue_results = []
    dequeue_results = []
    
    async with aiohttp.ClientSession() as session:
        print("Enqueuing messages...")
        for i in range(num_requests):
            queue_name = f"test_queue_{random.randint(1, 5)}"
            node_url = random.choice(BASE_URLS)
            
            start = time.time()
            try:
                async with session.post(
                    f"{node_url}/queue/enqueue",
                    json={
                        "queue_name": queue_name,
                        "message": {
                            "id": i,
                            "data": f"test_data_{i}",
                            "timestamp": time.time()
                        }
                    },
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    await resp.json()
                    duration = time.time() - start
                    enqueue_results.append({
                        "success": resp.status == 200,
                        "duration": duration
                    })
            except Exception as e:
                enqueue_results.append({
                    "success": False,
                    "duration": time.time() - start
                })
            
            if (i + 1) % 10 == 0:
                print(f"Enqueue progress: {i + 1}/{num_requests}")
        
        await asyncio.sleep(1)
        
        print("\nDequeuing messages...")
        for i in range(num_requests):
            queue_name = f"test_queue_{random.randint(1, 5)}"
            node_url = random.choice(BASE_URLS)
            
            start = time.time()
            try:
                async with session.post(
                    f"{node_url}/queue/dequeue",
                    json={
                        "queue_name": queue_name,
                        "consumer_id": f"consumer_{i}"
                    },
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    await resp.json()
                    duration = time.time() - start
                    dequeue_results.append({
                        "success": resp.status == 200,
                        "duration": duration
                    })
            except Exception as e:
                dequeue_results.append({
                    "success": False,
                    "duration": time.time() - start
                })
            
            if (i + 1) % 10 == 0:
                print(f"Dequeue progress: {i + 1}/{num_requests}")
    
    enqueue_success = sum(1 for r in enqueue_results if r["success"])
    dequeue_success = sum(1 for r in dequeue_results if r["success"])
    enqueue_durations = [r["duration"] for r in enqueue_results if r["success"]]
    dequeue_durations = [r["duration"] for r in dequeue_results if r["success"]]
    
    print(f"\n📊 Queue Test Results:")
    print(f"  Enqueue - Success: {enqueue_success}/{num_requests} ({enqueue_success/num_requests*100:.1f}%)")
    if enqueue_durations:
        print(f"  Enqueue - Avg time: {mean(enqueue_durations)*1000:.2f}ms")
    
    print(f"  Dequeue - Success: {dequeue_success}/{num_requests} ({dequeue_success/num_requests*100:.1f}%)")
    if dequeue_durations:
        print(f"  Dequeue - Avg time: {mean(dequeue_durations)*1000:.2f}ms")

async def test_cache_operations(num_requests=100):
    """Test operasi cache"""
    print("\n=== Testing Cache Operations ===")
    
    put_results = []
    get_results = []
    
    async with aiohttp.ClientSession() as session:
        print("Cache PUT operations...")
        for i in range(num_requests):
            key = f"key_{random.randint(1, 50)}"
            node_url = random.choice(BASE_URLS)
            
            start = time.time()
            try:
                async with session.post(
                    f"{node_url}/cache/put",
                    json={
                        "key": key,
                        "value": {
                            "id": i,
                            "data": f"value_{i}",
                            "timestamp": time.time()
                        }
                    },
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    await resp.json()
                    duration = time.time() - start
                    put_results.append({
                        "success": resp.status == 200,
                        "duration": duration
                    })
            except Exception as e:
                put_results.append({
                    "success": False,
                    "duration": time.time() - start
                })
            
            if (i + 1) % 10 == 0:
                print(f"PUT progress: {i + 1}/{num_requests}")
        
        await asyncio.sleep(0.5)
        
        print("\nCache GET operations...")
        for i in range(num_requests):
            key = f"key_{random.randint(1, 50)}"
            node_url = random.choice(BASE_URLS)
            
            start = time.time()
            try:
                async with session.get(
                    f"{node_url}/cache/get",
                    params={"key": key},
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    await resp.json()
                    duration = time.time() - start
                    get_results.append({
                        "success": resp.status == 200,
                        "duration": duration,
                        "found": resp.status == 200
                    })
            except Exception as e:
                get_results.append({
                    "success": False,
                    "duration": time.time() - start,
                    "found": False
                })
            
            if (i + 1) % 10 == 0:
                print(f"GET progress: {i + 1}/{num_requests}")
    
    put_success = sum(1 for r in put_results if r["success"])
    get_success = sum(1 for r in get_results if r["success"])
    cache_hits = sum(1 for r in get_results if r.get("found", False))
    put_durations = [r["duration"] for r in put_results if r["success"]]
    get_durations = [r["duration"] for r in get_results if r["success"]]
    
    print(f"\n📊 Cache Test Results:")
    print(f"  PUT - Success: {put_success}/{num_requests} ({put_success/num_requests*100:.1f}%)")
    if put_durations:
        print(f"  PUT - Avg time: {mean(put_durations)*1000:.2f}ms")
    
    print(f"  GET - Success: {get_success}/{num_requests} ({get_success/num_requests*100:.1f}%)")
    print(f"  GET - Cache hits: {cache_hits}/{num_requests} ({cache_hits/num_requests*100:.1f}%)")
    if get_durations:
        print(f"  GET - Avg time: {mean(get_durations)*1000:.2f}ms")

async def run_comprehensive_load_test():
    """Menjalankan semua load test"""
    print("=" * 60)
    print("  DISTRIBUTED SYSTEM LOAD TEST")
    print("=" * 60)
    print(f"\nTesting nodes: {', '.join(BASE_URLS)}")
    print("\nStarting comprehensive load test...")
    
    start_time = time.time()
    
    await test_lock_operations(num_requests=50)
    await test_queue_operations(num_requests=50)
    await test_cache_operations(num_requests=50)
    
    total_duration = time.time() - start_time
    
    print("\n" + "=" * 60)
    print(f"  LOAD TEST COMPLETED")
    print("=" * 60)
    print(f"Total duration: {total_duration:.2f} seconds")
    print(f"Total operations: 300 (50 lock + 100 queue + 100 cache)")
    print(f"Throughput: {300/total_duration:.2f} ops/sec")

if __name__ == "__main__":
    print("\n🚀 Starting Load Test Runner...")
    print("Pastikan Docker containers sudah berjalan!\n")
    
    asyncio.run(run_comprehensive_load_test())
