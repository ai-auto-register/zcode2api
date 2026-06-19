"""求解后立即用 verifyParam 发一次请求，避免一次性/过期干扰。"""

import asyncio
import base64
import json
import sys

sys.path.insert(0, ".")
from app import settings
from app.store import store
from app.agent import build_request
from app.captcha import captcha_manager
from app.solver_server import solver_server
from app.rnet_client import rnet_client


async def main():
    print(f"REVERSE_URL: {settings.REVERSE_URL!r}")
    print(f"USER_AGENT (业务头): {settings.USER_AGENT!r}")

    account = store.select("zai")
    if account is None:
        print("无可用 zai 账号"); return
    print(f"账号: {account.name} mode={account.mode} status={account.status}")

    callback_url = f"http://127.0.0.1:{settings.PORT}/internal/rnet-proxy"
    try:
        await solver_server.start(rnet_callback=callback_url)
        print(f"solver_server: {solver_server.base_url}")
    except Exception as e:
        print(f"solver_server 启动失败: {e}"); return

    try:
        # 求解
        captcha_manager.invalidate()
        t0 = asyncio.get_event_loop().time()
        try:
            verify_param = await captcha_manager.get_verify_param()
        except Exception as e:
            print(f"求解失败: {e}"); return
        t1 = asyncio.get_event_loop().time()
        print(f"\n求解耗时: {t1-t0:.2f}s, verifyParam 长度={len(verify_param)}")

        # 解码 JWT payload 看 certifyId/sceneId
        try:
            parts = verify_param.split(".")
            if len(parts) >= 2:
                pad = parts[1] + "=" * (-len(parts[1]) % 4)
                payload = json.loads(base64.urlsafe_b64decode(pad))
                print(f"verifyParam payload: {payload}")
        except Exception as e:
            print(f"解码失败: {e}")
            print(f"verifyParam 前 80 字符: {verify_param[:80]}")

        # 立即发请求（不先导无 verifyParam 请求）
        body = {
            "model": "GLM-5.2",
            "max_tokens": 16,
            "messages": [{"role": "user", "content": "hi"}],
        }
        url, headers = build_request(account, body, verify_param)
        url = settings.UPSTREAM["zai"]
        payload = json.dumps(body).encode("utf-8")
        print(f"\n--- 立即发请求（带正确 verifyParam）---")
        print(f"User-Agent 头: {headers.get('User-Agent')!r}")
        t2 = asyncio.get_event_loop().time()
        resp = await rnet_client.stream_post(url, headers, payload)
        t3 = asyncio.get_event_loop().time()
        status = resp.status_code
        status_int = status.as_int() if hasattr(status, "as_int") else int(status)
        data = await resp.bytes()
        text = data.decode("utf-8", "ignore")[:400]
        print(f"请求耗时: {t3-t2:.2f}s")
        print(f"status: {status_int}")
        print(f"body: {text}")
        if status_int == 200:
            print(">>> 成功！verifyParam 无感通过")
        elif status_int == 403 and "captcha" in text.lower():
            print(">>> 仍失败：verifyParam 被拒（可能绑定 IP/UA 不符，或 REVERSE_URL 影响）")
        await resp.close()
    finally:
        try: await solver_server.stop()
        except Exception: pass
        await rnet_client.close()


if __name__ == "__main__":
    asyncio.run(main())
