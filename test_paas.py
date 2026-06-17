import httpx
import asyncio

async def run():
    client = httpx.AsyncClient(verify=False)

    zcode_jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiZmNmMmU4MzctMjdkMi00MmJkLTg4YzEtODFjMjdiZTVmZGM5Iiwic3ViIjoiZmNmMmU4MzctMjdkMi00MmJkLTg4YzEtODFjMjdiZTVmZGM5IiwiaWF0IjoxNzgxNjE3MDY1fQ.qhA0_M40Q9iSUh5ms988LacYj9i9-mrtFLLJqR9eiWI"
    
    headers_jwt = {
        'Authorization': f'Bearer {zcode_jwt}',
        'anthropic-version': '2023-06-01',
        'Content-Type': 'application/json',
        'User-Agent': 'ZCode/unknown'
    }

    # Z.AI 官方逆向里，如果打向的是 paas 也就是 openai-compatible，可能会放行？
    print("--- Test 4: ZCode Plan PaaS Route (zcode.z.ai) glm-4.7 ---")
    payload_paas = {
        "model": "glm-4.7",
        "max_tokens": 100,
        "stream": False,
        "messages": [{"role": "user", "content": "你好，能听到吗"}]
    }

    # 测试 ZCode 的普通 openai 兼容路径
    res_paas = await client.post('https://zcode.z.ai/api/v1/zcode-plan/paas/v4/chat/completions', headers=headers_jwt, json=payload_paas)
    print("PAAS STATUS:", res_paas.status_code)
    print("PAAS BODY:", res_paas.text)

asyncio.run(run())