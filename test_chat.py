import httpx
import asyncio
from app.captcha import captcha_manager
from app.settings import PORT

async def run():
    client = httpx.AsyncClient(verify=False)
    
    headers = {
        'Authorization': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiNjU2MTQyMTYtZGI2Ny00OWU3LTg4NDItY2Q2ODRmNDBlZThkIiwic3ViIjoiNjU2MTQyMTYtZGI2Ny00OWU3LTg4NDItY2Q2ODRmNDBlZThkIiwiaWF0IjoxNzgxNjExNTQ3fQ.ATm04Wa2_jk_w5D3B0K0Fz1YYQPuZEUijho-ju5dNyQ',
        'anthropic-version': '2023-06-01',
        'Content-Type': 'application/json',
        'User-Agent': 'ZCode/unknown',
        'HTTP-Referer': 'https://zcode.z.ai',
        'X-Title': 'Z Code@electron'
    }
    
    # 尝试拿阿里云验证码
    try:
        verify_param = await captcha_manager.get_verify_param(PORT)
        print("Captcha parameter:", verify_param)
        if verify_param:
            headers['X-Aliyun-Captcha-Verify-Param'] = verify_param
            headers['X-Aliyun-Captcha-Verify-Region'] = 'cn'
    except Exception as e:
        print("Captcha Error:", e)
    
    payload = {
        "model": "glm-4.7",
        "max_tokens": 100,
        "stream": False,
        "messages": [{"role": "user", "content": [{"type": "text", "text": "只回复两个字：在的"}]}]
    }
    
    res = await client.post('https://zcode.z.ai/api/v1/zcode-plan/anthropic/v1/messages', headers=headers, json=payload)
    print("STATUS:", res.status_code)
    print("BODY:", res.text)
    
    await captcha_manager.close()

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
asyncio.run(run())
