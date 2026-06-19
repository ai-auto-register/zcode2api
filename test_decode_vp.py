"""解码真实抓包里的 verifyParam 与我们求解的对比。"""
import base64, json, sys
sys.path.insert(0, ".")
from app.captcha import captcha_manager
from app.solver_server import solver_server
from app.rnet_client import rnet_client
import asyncio, threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# 真实抓包的 verifyParam（从 _app_capture.log）
REAL = "eyJjZXJ0aWZ5SWQiOiJGMzhYbXFSNDVYIiwic2NlbmVJZCI6IjExeHlndHZkIiwiaXNTaWduIjp0cnVlLCJzZWN1cml0eVRva2VuIjoiNm9PbzdlNzJuQTYxdVZMaVpWS2lMWXFGMW05ck9ubzN2RUlQSkthTDdLTHhDSnFiMVVCd1JwbDRwN0VjRlRnZCtxcmpLMFd5emRjTDBzYXNxVkE1ZmNvWGsxYWdoSGJQdzVMaU9IeU1uYnBVU01Ya3BlQmFWZWlaRVI1N2VpVmEifQ=="

def decode(b64):
    pad = b64 + "=" * (-len(b64) % 4)
    return json.loads(base64.b64decode(pad))

print("真实 verifyParam 解码:")
print(json.dumps(decode(REAL), ensure_ascii=False, indent=2))
print(f"字段: {list(decode(REAL).keys())}")
print(f"长度: {len(REAL)}")
print()

# 现场求解一个对比
class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_POST(self):
        n=int(self.headers.get("content-length",0)); raw=self.rfile.read(n)
        import base64 as b64
        try:
            p=json.loads(raw); method=p.get("method","GET").upper(); url=p.get("url","")
            headers=p.get("headers") or {}; body=p.get("body")
            body_bytes = b64.b64decode(body) if body else None
            loop=asyncio.new_event_loop()
            try: st,hd,data=loop.run_until_complete(rnet_client.request(method,url,headers,body_bytes))
            finally: loop.close()
            out=json.dumps({"status":st,"headers":hd,"body":b64.b64encode(data).decode("ascii") if data else ""}).encode()
            self.send_response(200); self.send_header("content-type","application/json")
            self.send_header("content-length",str(len(out))); self.end_headers(); self.wfile.write(out)
        except Exception as e:
            out=json.dumps({"error":str(e)}).encode()
            self.send_response(502); self.send_header("content-type","application/json")
            self.send_header("content-length",str(len(out))); self.end_headers(); self.wfile.write(out)

httpd=HTTPServer(("127.0.0.1",0),H); threading.Thread(target=httpd.serve_forever,daemon=True).start()
port=httpd.server_address[1]

async def m():
    from app import settings
    settings.REVERSE_URL=""
    try: await solver_server.stop()
    except: pass
    await solver_server.start(rnet_callback=f"http://127.0.0.1:{port}/internal/rnet-proxy")
    captcha_manager.invalidate()
    try:
        vp=await captcha_manager.get_verify_param()
    except Exception as e:
        print(f"求解失败: {e}"); return
    print(f"\n我们求解的 verifyParam:")
    print(f"原始: {vp}")
    print(f"长度: {len(vp)}")
    try:
        d=decode(vp)
        print(f"解码: {json.dumps(d, ensure_ascii=False, indent=2)}")
        print(f"字段: {list(d.keys())}")
        print(f"有 securityToken: {'securityToken' in d}")
    except Exception as e:
        print(f"base64 解码失败: {e}")
    try: await solver_server.stop()
    except: pass
    await rnet_client.close()
    httpd.shutdown()

asyncio.run(m())
