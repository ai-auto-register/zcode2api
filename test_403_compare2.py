"""准确对比：monkey-patch settings.REVERSE_URL 控制 Node 求解走反代 vs 直连。"""

import asyncio
import base64
import json
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

sys.path.insert(0, ".")
from app import settings, logs
from app.store import store
from app.agent import build_request
from app.captcha import captcha_manager, CaptchaManager
from app.solver_server import solver_server
from app.rnet_client import rnet_client


class _State:
    reverse_url = ""
    calls = []


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
        if len(_State.calls) < 8:
            _State.calls.append(f"{method} {url[:100]}")
        ru = _State.reverse_url
        if ru and url.startswith("http") and not url.startswith(ru):
            url = ru + "/" + url
        loop = asyncio.new_event_loop()
        try:
            st, hd, data = loop.run_until_complete(rnet_client.request(method, url, headers, body))
        except Exception as e:
            self._send(502, {"error": str(e)}); return
        finally:
            loop.close()
        self._send(200, {"status": st, "headers": hd, "body": base64.b64encode(data).decode("ascii") if data else ""})
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_proxy_server(port=0):
    httpd = HTTPServer(("127.0.0.1", port), ProxyHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


async def solve_and_request(label: str, reverse_url: str):
    print(f"\n{'='*60}\n=== [{label}] REVERSE_URL={reverse_url or '(空,直连阿里云)'}\n{'='*60}")
    _State.reverse_url = reverse_url.rstrip("/")
    _State.calls = []
    # 关键：直接 patch settings.REVERSE_URL（_run_solver 读的就是这个）
    settings.REVERSE_URL = reverse_url

    account = store.select("zai")
    if account is None:
        print("无可用 zai 账号"); return
    try: await solver_server.stop()
    except Exception: pass
    proxy_port = proxy_httpd.server_address[1]
    callback_url = f"http://127.0.0.1:{proxy_port}/internal/rnet-proxy"
    try:
        await solver_server.start(rnet_callback=callback_url)
    except Exception as e:
        print(f"solver_server 启动失败: {e}"); return

    captcha_manager.invalidate()
    t0 = asyncio.get_event_loop().time()
    try:
        verify_param = await captcha_manager.get_verify_param()
    except Exception as e:
        print(f"求解失败: {e}")
        print("阿里云SDK请求:\n  " + "\n  ".join(_State.calls)); return
    t1 = asyncio.get_event_loop().time()
    print(f"求解耗时: {t1-t0:.2f}s, 长度={len(verify_param)}")
    print(f"verifyParam前80: {verify_param[:80]}")
    print("阿里云SDK请求:")
    for c in _State.calls: print(f"  {c}")
    try:
        parts = verify_param.split(".")
        if len(parts) >= 2:
            pad = parts[1] + "=" * (-len(parts[1]) % 4)
            p = json.loads(base64.urlsafe_b64decode(pad))
            print(f"payload: {p}")
    except Exception: print("(非JWT)")

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
        if si == 200: print(">>> 成功")
        elif si == 403 and "captcha" in text.lower(): print(">>> 失败:verifyParam被拒")
        await resp.close()
    except Exception as e:
        print(f"业务请求异常: {e}")


async def main():
    global proxy_httpd
    print(f"USER_AGENT(业务头): {settings.USER_AGENT!r}")
    proxy_httpd = start_proxy_server()
    # 保存原值
    orig = settings.REVERSE_URL
    try:
        await solve_and_request("走workers反代", orig)
        await asyncio.sleep(1)
        await solve_and_request("直连阿里云", "")
    finally:
        settings.REVERSE_URL = orig
        try: await solver_server.stop()
        except Exception: pass
        await rnet_client.close()
        proxy_httpd.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
