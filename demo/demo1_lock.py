import asyncio
import aiohttp

async def demo_locks():
    # URL untuk 3 lock manager nodes yang berjalan di Docker
    base_urls = [
        "http://localhost:15000",
        "http://localhost:15001",
        "http://localhost:15002"
    ]
    
    async def acquire_lock(node_url, resource_id, client_id, lock_type="exclusive", timeout=30):
        """Meminta lock pada resource tertentu"""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f"{node_url}/lock/acquire",
                    json={
                        "resource_id": resource_id,
                        "client_id": client_id,
                        "lock_type": lock_type,
                        "timeout": timeout
                    }
                ) as resp:
                    return await resp.json()
            except Exception as e:
                return {"success": False, "error": str(e)}
    
    async def release_lock(node_url, resource_id, client_id):
        """Melepaskan lock pada resource tertentu"""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f"{node_url}/lock/release",
                    json={
                        "resource_id": resource_id,
                        "client_id": client_id
                    }
                ) as resp:
                    return await resp.json()
            except Exception as e:
                return {"success": False, "error": str(e)}
    
    print("=== DEMO 1: Successful Lock Acquisition ===")
    # Client 1 acquire lock
    result1 = await acquire_lock(base_urls[0], "resource_A", "client1", "exclusive")
    print(f"Client1 acquire lock A: {result1.get('success', False)}")
    
    # Client 2 mencoba acquire - should wait
    print("\nClient2 trying to acquire same lock...")
    result2 = await acquire_lock(base_urls[1], "resource_A", "client2", "exclusive", timeout=2)
    print(f"Client2 acquire lock A: {result2.get('success', False)}")  # False - timeout
    
    # Client 1 release
    release_result = await release_lock(base_urls[0], "resource_A", "client1")
    print(f"Client1 released lock A: {release_result.get('success', False)}")
    
    await asyncio.sleep(0.5)
    
    # Client 2 retry - should succeed
    result2_retry = await acquire_lock(base_urls[1], "resource_A", "client2", "exclusive")
    print(f"Client2 acquire lock A: {result2_retry.get('success', False)}")  # True
    
    print("\n=== DEMO 2: Shared Locks ===")
    print("Multiple clients acquiring shared locks...")
    
    # Multiple clients dapat acquire shared lock
    result_s1 = await acquire_lock(base_urls[0], "resource_B", "client3", "shared")
    print(f"Client3 acquire shared lock B: {result_s1.get('success', False)}")
    
    result_s2 = await acquire_lock(base_urls[1], "resource_B", "client4", "shared")
    print(f"Client4 acquire shared lock B: {result_s2.get('success', False)}")
    
    result_s3 = await acquire_lock(base_urls[2], "resource_B", "client5", "shared")
    print(f"Client5 acquire shared lock B: {result_s3.get('success', False)}")
    
    # Exclusive lock will be blocked
    print("\nClient6 trying to acquire exclusive lock on same resource...")
    result_ex = await acquire_lock(base_urls[0], "resource_B", "client6", "exclusive", timeout=2)
    print(f"Client6 acquire exclusive lock B: {result_ex.get('success', False)}")  # Should be False
    
    print("\n✓ Demo selesai!")

asyncio.run(demo_locks())