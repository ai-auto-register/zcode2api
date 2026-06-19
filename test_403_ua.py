"""验证 verifyParam 是否绑定 UA/IP：求解和业务请求必须用同一个 rnet.Client 实例。"""

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


class _State:
    calls = []
    ua_seen = []
    remote_ip = None


class ProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        length = int(self.headers.get("content-length", 0))
        raw = self.rfile.read(length)
        payload = json.loads(raw)
        method = (payload.get("method") or "GET").upper()
        url = payload.get("url", "")
        headers = payload.get("headers") or {}
        body_b64 = payload.get("body")
        body = base64.b64decode(body_b64) if body_b64 else None
        # 记录求解阶段 rnet 发出请求时的 UA
        ua = headers.get("User-Agent") or headers.get("user-agent") or ""
        if ua and len(_State.ua_seen) < 3:
            _State.ua_seen.append(ua)
        if len(_State.calls) < 8:
            _State.calls.append(f"{method} {url[:100]} UA={ua[:30]}")
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


async def main():
    print(f"USER_AGENT(业务头): {settings.USER_AGENT!r}")
    settings.REVERSE_URL = ""  # 直连，排除反代干扰
    proxy_httpd = start_proxy_server()
    proxy_port = proxy_httpd.server_address[1]
    callback_url = f"http://127.0.0.1:{proxy_port}/internal/rnet-proxy"

    account = store.select("zai")
    print(f"账号: {account.name} mode={account.mode}")

    try: await solver_server.stop()
    except Exception: pass
    await solver_server.start(rnet_callback=callback_url)

    captcha_manager.invalidate()
    try:
        verify_param = await captcha_manager.get_verify_param()
    except Exception as e:
        print(f"求解失败: {e}"); return
    print(f"\nverifyParam长度={len(verify_param)}")
    print("求解阶段 rnet 发出的 UA:")
    for ua in _State.ua_seen: print(f"  {ua!r}")
    print("求解阶段请求:")
    for c in _State.calls: print(f"  {c}")

    # 业务请求
    body = {"model": "GLM-5.2", "max_tokens": 16, "messages": [{"role": "user", "content": "hi"}]}
    url, headers = build_request(account, body, verify_param)
    url = settings.UPSTREAM["zai"]
    print(f"\n业务请求头 User-Agent: {headers.get('User-Agent')!r}")
    print(f"业务请求头 X-Aliyun-Captcha-Verify-Param: {headers.get('X-Aliyun-Captcha-Verify-Param','')[:40]}...")
    payload = json.dumps(body).encode()
    resp = await rnet_client.stream_post(url, headers, payload)
    si = resp.status_code
    si = si.as_int() if hasattr(si, "as_int") else int(si)
    data = await resp.bytes()
    text = data.decode("utf-8", "ignore")[:400]
    print(f"\nstatus={si}")
    print(f"body: {text}")
    await resp.close()

    # 尝试2: 业务请求也用 ZCode UA 的 rnet（求解 UA 也是 Chrome131）
    # 关键：求解时 Node 用 Chrome131 UA，业务请求头是 ZCode/3.0.1——后端可能要求业务请求 UA == 求解 UA
    print("\n--- 尝试: 业务请求用 Chrome131 UA（与求解一致）---")
    captcha_manager.invalidate()
    try:
        verify_param2 = await captcha_manager.get_verify_param()
    except Exception as e:
        print(f"求解失败: {e}"); return
    url2, headers2 = build_request(account, body, verify_param2)
    url2 = settings.UPSTREAM["zai"]
    # 覆盖 UA 为 Chrome131
    chrome_ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    headers2["User-Agent"] = chrome_ua
    print(f"业务请求头 User-Agent: {headers2.get('User-Agent')!r}")
    payload2 = json.dumps(body).encode()
    resp2 = await rnet_client.stream_post(url2, headers2, payload2)
    si2 = resp2.status_code
    si2 = si2.as_int() if hasattr(si2, "as_int") else int(si2)
    data2 = await resp2.bytes()
    text2 = data2.decode("utf-8", "ignore")[:400]
    print(f"status={si2}")
    print(f"body: {text2}")
    if si2 == 200: print(">>> 用 Chrome131 UA 成功！根因是 UA 不一致")
    await resp2.close()

    try: await solver_server.stop()
    except Exception: pass
    await rnet_client.close()
    proxy_httpd.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
