"""复刻浏览器抓包里的完整请求头测试用户给的 verifyParam。"""
import asyncio, json, sys, sqlite3
sys.path.insert(0, ".")
from app import settings
from app.rnet_client import rnet_client

VP = "eyJjZXJ0aWZ5SWQiOiJMZzNDMlZGcHVBIiwic2NlbmVJZCI6IjExeHlndHZkIiwiaXNTaWduIjp0cnVlLCJzZWN1cml0eVRva2VuIjoiNm9PbzdlNzJuQTYxdVZMaVpWS2lMWXFGMW05ck9ubzN2RUlQSkthTDdLTHhDSnFiMVVCd1JwbDRwN0VjRlRnZG5PZWdGa3Z2clBHaC93RFZUMjRSR1NvWGsxYWdoSGJQdzVMaU9IeU1uYnBVU01Ya3BlQmFWZWlaRVI1N2VpVmEifQ=="

# 读账号 JWT
c = sqlite3.connect(r"D:\code\zcode2api\data\accounts.db")
c.row_factory = sqlite3.Row
r = c.execute("SELECT data FROM accounts WHERE id='zai-1-6fe58004'").fetchone()
jwt_token = json.loads(r["data"])["jwt_token"]

# 完整复刻浏览器抓包的请求头
URL = settings.UPSTREAM["zai"]
headers = {
    "content-type": "application/json",
    "anthropic-version": "2023-06-01",
    "authorization": f"Bearer {jwt_token}",
    "http-referer": "https://zcode.z.ai",
    "user-agent": "ZCode/3.1.1 ai-sdk/provider-utils/4.0.27 runtime/node.js/24",
    "x-aliyun-captcha-verify-param": VP,
    "x-aliyun-captcha-verify-region": "sgp",
    "x-zcode-agent": "glm",
    "x-zcode-app-version": "3.1.1",
    "x-title": "Z Code@electron",
    "x-query-id": "test-query-id",
    "x-request-id": "test-request-id",
    "x-session-id": "test-session-id",
    "x-zcode-trace-id": "test-trace-id",
}

body = {"model": "GLM-5.2", "max_tokens": 16, "messages": [{"role": "user", "content": "hi"}]}
payload = json.dumps(body).encode()

async def main():
    print(f"target: {URL}")
    print(f"UA: {headers['user-agent']!r}")
    print(f"VP前40: {VP[:40]}...")
    resp = await rnet_client.stream_post(URL, headers, payload)
    si = resp.status_code
    si = si.as_int() if hasattr(si, "as_int") else int(si)
    data = await resp.bytes()
    text = data.decode("utf-8", "ignore")[:500]
    print(f"\nstatus: {si}")
    print(f"body: {text}")
    if si == 200:
        print(">>> 成功！完整请求头有效")
    elif si == 403 and "captcha" in text.lower():
        print(">>> 失败")
    await resp.close()
    await rnet_client.close()

asyncio.run(main())
