"""测试 camoufox 求解器：求解 verifyParam 后立即发业务请求验证。"""
import asyncio
import base64
import json
import sys

sys.path.insert(0, ".")
from app import settings
from app.store import store
from app.agent import build_request
from app.captcha import captcha_manager
from app.rnet_client import rnet_client


async def main():
    # 强制用 camoufox
    settings.CAPTCHA_SOLVER = "camoufox"
    print(f"CAPTCHA_SOLVER: {settings.CAPTCHA_SOLVER}")
    print(f"CAMOUFOX_HEADLESS: {settings.CAMOUFOX_HEADLESS}")
    print(f"CAMOUFOX_SOLVE_TIMEOUT: {settings.CAMOUFOX_SOLVE_TIMEOUT}s")

    account = store.select("zai")
    if not account:
        print("无可用 zai 账号"); return
    print(f"账号: {account.name} mode={account.mode}")

    # 1. 求解
    captcha_manager.invalidate()
    t0 = asyncio.get_event_loop().time()
    try:
        verify_param = await captcha_manager.get_verify_param()
    except Exception as e:
        print(f"求解失败: {e}")
        await captcha_manager.close()
        return
    t1 = asyncio.get_event_loop().time()
    print(f"\n求解耗时: {t1-t0:.2f}s, 长度={len(verify_param)}")

    # 解码看结构
    try:
        pad = verify_param + "=" * (-len(verify_param) % 4)
        p = json.loads(base64.b64decode(pad))
        print(f"verifyParam 解码: {json.dumps(p, ensure_ascii=False)}")
        print(f"字段: {list(p.keys())}")
        print(f"有 securityToken: {'securityToken' in p}")
    except Exception as e:
        print(f"解码失败: {e}")
        print(f"verifyParam 前 100: {verify_param[:100]}")

    # 2. 立即发业务请求
    body = {"model": "GLM-5.2", "max_tokens": 16, "messages": [{"role": "user", "content": "hi"}]}
    url, headers = build_request(account, body, verify_param)
    url = settings.UPSTREAM["zai"]
    payload = json.dumps(body).encode()
    t2 = asyncio.get_event_loop().time()
    try:
        resp = await rnet_client.stream_post(url, headers, payload)
        si = resp.status_code
        si = si.as_int() if hasattr(si, "as_int") else int(si)
        data = await resp.bytes()
        text = data.decode("utf-8", "ignore")[:400]
        t3 = asyncio.get_event_loop().time()
        print(f"\n业务请求: {t3-t2:.2f}s | status={si}")
        print(f"body: {text}")
        if si == 200:
            print(">>> 成功！camoufox 求解的 verifyParam 通过无感验证")
        elif si == 403 and "captcha" in text.lower():
            print(">>> 失败：verifyParam 被上游拒绝")
        await resp.close()
    except Exception as e:
        print(f"业务请求异常: {e}")

    await captcha_manager.close()
    await rnet_client.close()


if __name__ == "__main__":
    asyncio.run(main())
