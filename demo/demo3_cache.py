import asyncio
import aiohttp
import time

async def demo_cache():
    # URL untuk 3 cache nodes yang berjalan di Docker
    base_urls = [
        "http://localhost:15000",
        "http://localhost:15001",
        "http://localhost:15002"
    ]
    
    async def cache_put(node_url, key, value):
        """Menyimpan data ke cache"""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f"{node_url}/cache/put",
                    json={
                        "key": key,
                        "value": value
                    }
                ) as resp:
                    return await resp.json()
            except Exception as e:
                return {"success": False, "error": str(e)}
    
    async def cache_get(node_url, key):
        """Mengambil data dari cache"""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"{node_url}/cache/get",
                    params={"key": key}
                ) as resp:
                    return await resp.json()
            except Exception as e:
                return {"found": False, "value": None, "error": str(e)}
    
    print("=== DEMO: Cache Read/Write ===")
    
    # Node 1 writes data
    result = await cache_put(base_urls[0], "user:1001", {"name": "Alice", "age": 25})
    print(f"Node 1 wrote user:1001: {result.get('success', False)}")
    
    await asyncio.sleep(0.5)
    
    # Node 2 reads same data
    data = await cache_get(base_urls[1], "user:1001")
    if data.get("found"):
        print(f"Node 2 read user:1001: {data.get('value')}")
    else:
        print("Node 2: Cache miss")
    
    print("\n=== DEMO: Cache Invalidation ===")
    
    # Node 3 modifies data
    print("Node 3 modifying user:1001...")
    result_mod = await cache_put(base_urls[2], "user:1001", {"name": "Alice", "age": 26})
    print(f"Modification result: {result_mod.get('success', False)}")
    
    await asyncio.sleep(0.5)  # Wait for invalidation broadcast
    
    # Check states di semua nodes
    print("\nCache states after modification:")
    for i, url in enumerate(base_urls, 1):
        data = await cache_get(url, "user:1001")
        if data.get("found"):
            print(f"Node {i}: {data.get('value')}")
        else:
            print(f"Node {i}: Cache miss or invalidated")
    
    print("\n=== DEMO: Cache Performance ===")
    
    # Populate cache
    print("Populating cache with 100 entries...")
    for i in range(100):
        node_url = base_urls[i % len(base_urls)]
        await cache_put(node_url, f"key_{i}", {"value": i})
    
    # Read performance test
    start = time.time()
    hits = 0
    
    for i in range(100):
        node_url = base_urls[i % len(base_urls)]
        data = await cache_get(node_url, f"key_{i}")
        if data.get("found"):
            hits += 1
    
    duration = time.time() - start
    
    print(f"\n📊 Performance Metrics:")
    print(f"- Total reads: 100")
    print(f"- Cache hits: {hits}")
    print(f"- Hit rate: {(hits/100)*100:.1f}%")
    print(f"- Duration: {duration:.3f}s")
    print(f"- Throughput: {100/duration:.0f} ops/sec")
    
    print("\n✓ Demo selesai!")

asyncio.run(demo_cache())