import httpx
import asyncio

async def run():
    client = httpx.AsyncClient(verify=False)
    
    # 按照文档说明，Start Plan 有两个可能，这个是在 JSON 里看到的 API Key
    # {"apiKey": "5a76d3bd30ce40e68201d7201110908a.iBNBrKIIKQYzyxRH", "baseURL": "https://api.z.ai/api/anthropic"}
    api_key = "5a76d3bd30ce40e68201d7201110908a.iBNBrKIIKQYzyxRH"
    
    headers_apikey = {
        'x-api-key': api_key,
        'anthropic-version': '2023-06-01',
        'Content-Type': 'application/json',
        'User-Agent': 'ZCode/unknown'
    }

    payload = {
        "model": "glm-5.2",
        "max_tokens": 100,
        "stream": False,
        "messages": [{"role": "user", "content": [{"type": "text", "text": "你好，能听到吗"}]}]
    }

    # 测试 1: 使用 API Key 打 api.z.ai
    print("--- Test 1: API Key Route (api.z.ai) glm-5.2 ---")
    res1 = await client.post('https://api.z.ai/api/anthropic/v1/messages', headers=headers_apikey, json=payload)
    print("STATUS:", res1.status_code)
    print("BODY:", res1.text)

asyncio.run(run())
