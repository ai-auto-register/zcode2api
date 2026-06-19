"""测试使用正确的 verifyParam 请求上游，观察是否还出现 captcha failed 403。

流程：
1. 启动 Node solver_server（带 rnet 回调）
2. 通过 captcha_manager 求解真实 verifyParam
3. 用 rnet (Chrome131) 发起 zcode /messages 请求
4. 对比：不带头 vs 带正确 verifyParam
"""

import asyncio
import json
import sys

import httpx

sys.path.insert(0, ".")
from app import settings
from app.store import store
from app.agent import build_request
from app.captcha import captcha_manager
from app.solver_server import solver_server
from app.rnet_client import rnet_client


async def send_request(label: str, account, body: dict, verify_param: str | None):
    print(f"\n=== [{label}] verify_param={'有' if verify_param else '无'} ===")
    try:
        url, headers = build_request(account, body, verify_param)
    except RuntimeError as e:
        print(f"    build_request 失败: {e}")
        return

    url = settings.UPSTREAM["zai"]
    payload = json.dumps(body).encode("utf-8")
    print(f"    target: {url}")
    print(f"    has verify header: {'X-Aliyun-Captcha-Verify-Param' in headers}")

    try:
        resp = await rnet_client.stream_post(url, headers, payload)
        status = resp.status_code
        status_int = status.as_int() if hasattr(status, "as_int") else int(status)
        data = await resp.bytes()
        text = data.decode("utf-8", "ignore")[:500]
        print(f"    status: {status_int}")
        print(f"    body: {text}")
        low = text.lower()
        is_captcha = "captcha" in low or "verify token" in low or "verify failed" in low
        print(f"    _is_captcha_error: {is_captcha}")
        if status_int == 200:
            print("    >>> 成功！验证码无感通过")
        elif status_int == 403 and is_captcha:
            print("    >>> 会触发 '验证码失效，刷新重试'")
        await resp.close()
    except Exception as e:
        print(f"    请求异常: {e}")


async def main():
    print(f"REVERSE_URL: {settings.REVERSE_URL!r}")
    print(f"SOLVER_SERVER_ENABLED: {settings.SOLVER_SERVER_ENABLED}")
    print(f"SOLVER_PROXY_ZAI: {settings.SOLVER_PROXY_ZAI}")

    account = store.select("zai")
    if account is None:
        print("无可用 zai 账号")
        return
    print(f"账号: {account.name} mode={account.mode} provider={account.provider} status={account.status}")

    body = {
        "model": "GLM-5.2",
        "max_tokens": 16,
        "messages": [{"role": "user", "content": "hi"}],
    }

    # 1. 启动 Node solver 服务（带 rnet 回调，让求解阶段也走 Chrome131）
    callback_url = f"http://127.0.0.1:{settings.PORT}/internal/rnet-proxy"
    try:
        await solver_server.start(rnet_callback=callback_url)
        print(f"solver_server 已启动: {solver_server.base_url}")
    except Exception as e:
        print(f"solver_server 启动失败: {e}")
        return

    try:
        # 2. 求解真实 verifyParam
        print("\n--- 开始求解 verifyParam ---")
        captcha_manager.invalidate()
        try:
            verify_param = await captcha_manager.get_verify_param()
            print(f"求解成功，verifyParam 长度={len(verify_param)}")
            print(f"verifyParam 前 40 字符: {verify_param[:40]}...")
        except Exception as e:
            print(f"求解失败: {e}")
            return

        # 3. 场景A: 不带 verifyParam（应触发 403 captcha failed）
        await send_request("无 verifyParam", account, body, None)

        # 4. 场景B: 带正确 verifyParam（应 200 成功）
        await send_request("正确 verifyParam", account, body, verify_param)
    finally:
        await solver_server.stop()
        await rnet_client.close()


if __name__ == "__main__":
    asyncio.run(main())
