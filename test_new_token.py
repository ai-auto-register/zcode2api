import httpx
import asyncio
from app.captcha import captcha_manager
from app.settings import PORT

async def run():
    client = httpx.AsyncClient(verify=False)
    
    # 根据你提供的配置信息，有两组凭证：
    # 1. API Key 路线（打向 api.z.ai）
    api_key = "5a76d3bd30ce40e68201d7201110908a.iBNBrKIIKQYzyxRH"
    
    headers_apikey = {
        'x-api-key': api_key,
        'anthropic-version': '2023-06-01',
        'Content-Type': 'application/json',
        'User-Agent': 'ZCode/unknown'
    }

    # 2. ZCode JWT 路线（打向 zcode.z.ai Start Plan 网关）
    zcode_jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiZmNmMmU4MzctMjdkMi00MmJkLTg4YzEtODFjMjdiZTVmZGM5Iiwic3ViIjoiZmNmMmU4MzctMjdkMi00MmJkLTg4YzEtODFjMjdiZTVmZGM5IiwiaWF0IjoxNzgxNjE3MDY1fQ.qhA0_M40Q9iSUh5ms988LacYj9i9-mrtFLLJqR9eiWI"
    
    headers_jwt = {
        'Authorization': f'Bearer {zcode_jwt}',
        'anthropic-version': '2023-06-01',
        'Content-Type': 'application/json',
        'User-Agent': 'ZCode/unknown',
        'HTTP-Referer': 'https://zcode.z.ai',
        'X-Title': 'Z Code@electron'
    }

    payload = {
        "model": "glm-5.2",
        "max_tokens": 100,
        "stream": False,
        "messages": [{"role": "user", "content": [{"type": "text", "text": "你好，能听到吗"}]}]
    }

    # 测试 2: 使用 ZCode JWT 打 zcode.z.ai
    print("\n--- Test 2: ZCode JWT Route (zcode.z.ai) (Model: glm-5.2) ---")
    
    try:
        verify_param = await captcha_manager.get_verify_param(PORT)
        if verify_param:
            headers_jwt['X-Aliyun-Captcha-Verify-Param'] = verify_param
            headers_jwt['X-Aliyun-Captcha-Verify-Region'] = 'cn'
    except Exception as e:
        print("Captcha error:", e)
        
    res2 = await client.post('https://zcode.z.ai/api/v1/zcode-plan/anthropic/v1/messages', headers=headers_jwt, json=payload)
    print("STATUS:", res2.status_code)
    print("BODY:", res2.text)
    
    # 顺便查一下这组 token 的额度
    print("\n--- Test 3: Check Quota (zcode.z.ai) ---")
    res_b1 = await client.get('https://zcode.z.ai/api/v1/zcode-plan/billing/current', headers={'Authorization': f'Bearer {zcode_jwt}'})
    print("BILLING (current):", res_b1.status_code, res_b1.text)

    res_b2 = await client.get('https://zcode.z.ai/api/v1/zcode-plan/billing/balance', headers={'Authorization': f'Bearer {zcode_jwt}'})
    print("BILLING (balance):", res_b2.status_code, res_b2.text)

    await captcha_manager.close()

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
asyncio.run(run())
