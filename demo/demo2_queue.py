import asyncio
import aiohttp
import time

async def demo_queue():
    # URL untuk 3 queue nodes yang berjalan di Docker
    base_urls = [
        "http://localhost:15000",
        "http://localhost:15001",
        "http://localhost:15002"
    ]
    
    async def enqueue(node_url, queue_name, message):
        """Mengirim pesan ke queue"""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f"{node_url}/queue/enqueue",
                    json={
                        "queue_name": queue_name,
                        "message": message
                    }
                ) as resp:
                    return await resp.json()
            except Exception as e:
                return {"success": False, "error": str(e)}
    
    async def dequeue(node_url, queue_name, consumer_group="default"):
        """Mengambil pesan dari queue"""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f"{node_url}/queue/dequeue",
                    json={
                        "queue_name": queue_name,
                        "consumer_group": consumer_group
                    }
                ) as resp:
                    return await resp.json()
            except Exception as e:
                return {"success": False, "message": None, "error": str(e)}
    
    print("=== DEMO: Multiple Producers ===")
    
    # Multiple producers mengirim messages
    async def producer(producer_id, count):
        for i in range(count):
            message = {
                "id": f"msg_{producer_id}_{i}",
                "data": f"Data from producer {producer_id}",
                "timestamp": time.time()
            }
            node_url = base_urls[producer_id % len(base_urls)]
            result = await enqueue(node_url, "orders", message)
            if result.get("success"):
                print(f"Producer {producer_id} sent: {message['id']}")
            await asyncio.sleep(0.1)
    
    # Start 3 producers
    producers = [
        asyncio.create_task(producer(i, 5))
        for i in range(1, 4)
    ]
    
    await asyncio.gather(*producers)
    
    print("\n✓ All producers finished sending messages")
    
    print("\n=== DEMO: Multiple Consumers ===")
    
    # Multiple consumers memproses messages
    async def consumer(consumer_id, count):
        for _ in range(count):
            node_url = base_urls[consumer_id % len(base_urls)]
            result = await dequeue(node_url, "orders", consumer_group=f"group_{consumer_id}")
            if result.get("success") and result.get("message"):
                message = result["message"]
                print(f"Consumer {consumer_id} received: {message.get('id', 'unknown')}")
                # Simulate processing
                await asyncio.sleep(0.2)
    
    # Start 2 consumers
    consumers = [
        asyncio.create_task(consumer(i, 7))
        for i in range(1, 3)
    ]
    
    await asyncio.gather(*consumers)
    
    print("\n✓ All consumers finished processing messages")
    print("\n✓ Demo selesai!")

asyncio.run(demo_queue())