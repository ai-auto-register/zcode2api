import httpx
import asyncio
import secrets
import urllib.parse
from app.captcha import captcha_manager

WEB_JWT = "eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6Ijc0YjhiMTMwLTQzNjgtNDllYS1hY2UxLTM4OGEyZjhkZmIwZSIsImVtYWlsIjoicmhheWVzNjYzQHRvcHJlbi5jeW91In0.LjbgHSxDWKO4dUJIZHpX7ozOXoTAfrH9JuqqDp-Gyju0pRjpLrFVyPNT7EZPA3tfUoy1HZXgHXQwQa7nz97YWw"
CLIENT_ID = "client_P8X5CMWmlaRO9gyO-KSqtg"

async def run():
    client = httpx.AsyncClient(verify=False)
    
    # Step 1
    state = secrets.token_hex(16)
    res1 = await client.post(
        "https://chat.z.ai/api/oauth/authorize",
        headers={"Authorization": f"Bearer {WEB_JWT}", "x-region": "overseas"},
        data={
            "client_id": CLIENT_ID,
            "redirect_uri": "zcode://zai-auth/callback",
            "state": state,
            "response_type": "code",
            "action": "approve"
        }
    )
    if res1.status_code != 200: return
    data1 = res1.json()
    redirect_url = data1.get("redirect_url", "")
    parsed = urllib.parse.urlparse(redirect_url)
    qs = urllib.parse.parse_qs(parsed.query)
    code = qs.get("code", [""])[0]
    
    # Step 2
    res2 = await client.post(
        "https://zcode.z.ai/api/v1/oauth/token",
        json={
            "provider": "zai",
            "code": code,
            "redirect_uri": "zcode://zai-auth/callback",
            "state": state
        }
    )
    if res2.status_code != 200: return
    data2 = res2.json()
    zcodeJwt = data2.get("data", {}).get("token")
    
    # Test Chat
    headers = {
        'Authorization': f'Bearer {zcodeJwt}',
        'anthropic-version': '2023-06-01',
        'Content-Type': 'application/json',
        'User-Agent': 'ZCode/unknown'
    }
    
    try:
        verify_param = await captcha_manager.get_verify_param(3000)
        if verify_param:
            headers['X-Aliyun-Captcha-Verify-Param'] = verify_param
            headers['X-Aliyun-Captcha-Verify-Region'] = 'cn'
    except Exception as e:
        print("Captcha error:", e)
        
    payload = {
        "model": "glm-4.7",
        "max_tokens": 100,
        "stream": False,
        "messages": [{"role": "user", "content": [{"type": "text", "text": "你好"}]}]
    }
    
    res_chat = await client.post('https://zcode.z.ai/api/v1/zcode-plan/anthropic/v1/messages', headers=headers, json=payload)
    print("CHAT STATUS:", res_chat.status_code)
    print("CHAT BODY:", res_chat.text)
    await captcha_manager.close()

asyncio.run(run())
