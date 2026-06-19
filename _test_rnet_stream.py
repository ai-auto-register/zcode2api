import rnet
import asyncio
import json
import time

async def test():
    c = rnet.Client(impersonate=rnet.Impersonate.Chrome131)
    
    body = {
        "model": "GLM-5.2",
        "max_tokens": 50,
        "stream": True,
        "messages": [{"role": "user", "content": [{"type": "text", "text": "say hi"}]}],
    }
    headers = {"content-type": "application/json", "anthropic-version": "2023-06-01"}

    print("Sending streaming POST...")
    t0 = time.time()
    resp = await c.post("https://api.z.ai/api/anthropic/v1/messages", headers=headers, json=body)
    t1 = time.time()
    print(f"Response received in {t1-t0:.2f}s, status={resp.status_code}")
    
    # Test 1: current approach in _RnetResponseShim
    print("\n--- Test 1: stream() + await __aiter__() ---")
    stream = resp.stream()
    it = await stream.__aiter__()
    count = 0
    t2 = time.time()
    async for chunk in it:
        count += 1
        elapsed = time.time() - t2
        print(f"  chunk {count} at {elapsed:.3f}s: {len(chunk)} bytes: {chunk[:80]}")
        if count > 5:
            break
    print(f"Total chunks: {count}")
    await resp.close()

asyncio.run(test())
