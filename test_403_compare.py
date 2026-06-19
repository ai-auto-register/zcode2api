"""自包含测试：对比 REVERSE_URL 反代 vs 直连阿里云 求解的 verifyParam 有效性。

不依赖 3000 端口的 FastAPI，自己内嵌一个 rnet-proxy 回调 HTTP 服务。
"""

import asyncio
import base64
import json
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

sys.path.insert(0, ".")
from app import settings
from app.store import store
from app.agent import build_request
from app.captcha import captcha_manager
from app.solver_server import solver_server
from app.rnet_client import rnet_client


# 内嵌一个简易 rnet-proxy 回调服务器，REVERSE_URL 可动态控制
class _State:
    reverse_url = settings.REVERSE_URL.rstrip("/")  # 初始用 .env 的值
    calls = []  # 记录求解时阿里云 SDK 请求的 URL


class ProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_POST(self):
        length = int(self.headers.get("content-length", 0))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw)
        except Exception:
            self._send(400, {"error": "invalid json"}); return
        method = (payload.get("method") or "GET").upper()
        url = payload.get("url", "")
        headers = payload.get("headers") or {}
        body_b64 = payload.get("body")
        body = base64.b64decode(body_b64) if body_b64 else None

        # 记录求解时阿里云 SDK 请求的 URL（前 3 个）
        if len(_State.calls) < 6:
            _State.calls.append(f"{method} {url[:90]}")

        # 应用 REVERSE_URL 前缀（与 internal_api.py 逻辑一致）
        ru = _State.reverse_url
        if ru and url.startswith("http") and not url.startswith(ru):
            url = ru + "/" + url

        try:
            # 用 asyncio run 调 rnet（同步 handler 里调异步）
            loop = asyncio.new_event_loop()
            try:
                st, hd, data = loop.run_until_complete(
                    rnet_client.request(method, url, headers, body)
                )
            finally:
                loop.close()
        except Exception as e:
            self._send(502, {"error": str(e)}); return

        self._send(200, {
            "status": st,
            "headers": hd,
            "body": base64.b64encode(data).decode("ascii") if data else "",
        })

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_proxy_server(port=0):
    httpd = HTTPServer(("127.0.0.1", port), ProxyHandler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd


async def solve_and_request(label: str, reverse_url: str):
    print(f"\n{'='*60}")
    print(f"=== [{label}] REVERSE_URL={reverse_url or '(空，直连阿里云)'} ===")
    print(f"{'='*60}")
    _State.reverse_url = reverse_url.rstrip("/")
    _State.calls = []

    account = store.select("zai")
    if account is None:
        print("无可用 zai 账号"); return
    # 强制重置 solver_server，用新的 callback
    try: await solver_server.stop()
    except Exception: pass

    proxy_port = proxy_httpd.server_address[1]
    callback_url = f"http://127.0.0.1:{proxy_port}/internal/rnet-proxy"
    # 用一个假 token（我们的简易 handler 不校验）
    try:
        await solver_server.start(rnet_callback=callback_url)
    except Exception as e:
        print(f"solver_server 启动失败: {e}"); return

    # solver_server.start 设置了 _callback_token，但我们的 handler 不校验
    # 需要把 callback_token 传给 Node，start 已通过 env RNET_CALLBACK_TOKEN 传了

    captcha_manager.invalidate()
    t0 = asyncio.get_event_loop().time()
    try:
        verify_param = await captcha_manager.get_verify_param()
    except Exception as e:
        print(f"求解失败: {e}")
        print(f"求解时阿里云 SDK 请求列表:\n  " + "\n  ".join(_State.calls))
        return
    t1 = asyncio.get_event_loop().time()
    print(f"求解耗时: {t1-t0:.2f}s, 长度={len(verify_param)}")
    print(f"verifyParam 前 80 字符: {verify_param[:80]}")
    print(f"求解时阿里云 SDK 请求列表:")
    for c in _State.calls:
        print(f"  {c}")

    # 解码 payload
    try:
        parts = verify_param.split(".")
        if len(parts) >= 2:
            pad = parts[1] + "=" * (-len(parts[1]) % 4)
            p = json.loads(base64.urlsafe_b64decode(pad))
            print(f"verifyParam payload: {p}")
    except Exception:
        print("(非 JWT 格式或解码失败)")

    # 立即发业务请求
    body = {"model": "GLM-5.2", "max_tokens": 16, "messages": [{"role": "user", "content": "hi"}]}
    url, headers = build_request(account, body, verify_param)
    url = settings.UPSTREAM["zai"]
    payload = json.dumps(body).encode()
    t2 = asyncio.get_event_loop().time()
    try:
        resp = await rnet_client.stream_post(url, headers, payload)
        status = resp.status_code
        si = status.as_int() if hasattr(status, "as_int") else int(status)
        data = await resp.bytes()
        text = data.decode("utf-8", "ignore")[:400]
        t3 = asyncio.get_event_loop().time()
        print(f"\n业务请求耗时: {t3-t2:.2f}s")
        print(f"status: {si}")
        print(f"body: {text}")
        if si == 200:
            print(">>> 成功！")
        elif si == 403 and "captcha" in text.lower():
            print(">>> 失败：verifyParam 被上游拒绝")
        await resp.close()
    except Exception as e:
        print(f"业务请求异常: {e}")


async def main():
    print(f"USER_AGENT(业务头): {settings.USER_AGENT!r}")
    global proxy_httpd
    proxy_httpd = start_proxy_server()

    try:
        # 测试1: 走 .env 配置的 workers 反代
        await solve_and_request("走 workers 反代", settings.REVERSE_URL)

        await asyncio.sleep(1)

        # 测试2: 直连阿里云（REVERSE_URL 为空）
        await solve_and_request("直连阿里云", "")
    finally:
        try: await solver_server.stop()
        except Exception: pass
        await rnet_client.close()
        proxy_httpd.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
