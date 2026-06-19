"""用用户提供的完整 verifyParam（含 securityToken）测试是否能通过。"""
import asyncio, json, sys
sys.path.insert(0, ".")
from app import settings
from app.store import store
from app.agent import build_request
from app.rnet_client import rnet_client

VP = "eyJjZXJ0aWZ5SWQiOiJMZzNDMlZGcHVBIiwic2NlbmVJZCI6IjExeHlndHZkIiwiaXNTaWduIjp0cnVlLCJzZWN1cml0eVRva2VuIjoiNm9PbzdlNzJuQTYxdVZMaVpWS2lMWXFGMW05ck9ubzN2RUlQSkthTDdLTHhDSnFiMVVCd1JwbDRwN0VjRlRnZG5PZWdGa3Z2clBHaC93RFZUMjRSR1NvWGsxYWdoSGJQdzVMaU9IeU1uYnBVU01Ya3BlQmFWZWlaRVI1N2VpVmEifQ=="

async def main():
    account = store.select("zai")
    if not account:
        print("无可用 zai 账号"); return
    print(f"账号: {account.name} mode={account.mode}")
    body = {"model": "GLM-5.2", "max_tokens": 16, "messages": [{"role": "user", "content": "hi"}]}
    url, headers = build_request(account, body, VP)
    url = settings.UPSTREAM["zai"]
    payload = json.dumps(body).encode()
    print(f"target: {url}")
    print(f"UA: {headers.get('User-Agent')!r}")
    resp = await rnet_client.stream_post(url, headers, payload)
    si = resp.status_code
    si = si.as_int() if hasattr(si, "as_int") else int(si)
    data = await resp.bytes()
    text = data.decode("utf-8", "ignore")[:500]
    print(f"status: {si}")
    print(f"body: {text}")
    if si == 200:
        print(">>> 成功！含 securityToken 的 verifyParam 通过")
    elif si == 403 and "captcha" in text.lower():
        print(">>> 失败：即使含 securityToken 也被拒（可能过期或 IP 绑定）")
    await resp.close()
    await rnet_client.close()

asyncio.run(main())
