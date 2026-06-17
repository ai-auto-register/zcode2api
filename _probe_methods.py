"""穷举 HTTP 方法 + 看真实 Allow 头，定位 405。"""
import subprocess, json, sys, time, http.client, ssl

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiNzRiOGIxMzAtNDM2OC00OWVhLWFjZTEtMzg4YTJmOGRmYjBlIiwic3ViIjoiNzRiOGIxMzAtNDM2OC00OWVhLWFjZTEtMzg4YTJmOGRmYjBlIiwiaWF0IjoxNzgxNjE5MjgzfQ.GLIjAsmbbBuo0jX2S4-9Dh-5FMRbxAaQ6b5okq3yQN0"
PATH = "/api/v1/zcode-plan/anthropic/v1/messages"

def solve(retries=4):
    for _ in range(retries):
        p = subprocess.run(["node", "solver.js", "11xygtvd", "sgp", "no8xfe"],
            cwd=r"D:\ptuer\zcode2api\captcha_node", capture_output=True, text=True, timeout=40)
        for line in p.stdout.splitlines():
            if line.startswith("VERIFY_PARAM="):
                return line[len("VERIFY_PARAM="):].strip()
        time.sleep(1)
    return None

def raw(method, body=None, vp=None):
    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection("zcode.z.ai", timeout=30, context=ctx)
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
        "X-ZCode-App-Version": "3.0.1",
        "X-ZCode-Agent": "glm",
        "HTTP-Referer": "https://zcode.z.ai/",
        "User-Agent": "ZCode/3.0.1",
        "Host": "zcode.z.ai",
    }
    if vp:
        headers["X-Aliyun-Captcha-Verify-Param"] = vp
    data = json.dumps(body).encode() if body is not None else None
    conn.request(method, PATH, body=data, headers=headers)
    r = conn.getresponse()
    txt = r.read().decode("utf-8", "ignore")
    allow = r.getheader("Allow") or r.getheader("allow") or ""
    acam = r.getheader("Access-Control-Allow-Methods") or ""
    conn.close()
    return r.status, allow, acam, txt[:200]

if __name__ == "__main__":
    # 1. 不带 body 探测每个方法的真实响应 + Allow 头
    print("=== 不带 captcha 的方法探测 ===")
    for m in ["OPTIONS", "GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"]:
        try:
            st, allow, acam, txt = raw(m)
            print(f"[{m:8}] {st}  allow={allow!r}  acam={acam!r}  body={txt[:120]}")
        except Exception as e:
            print(f"[{m:8}] ERR {e}")
        time.sleep(0.3)

    # 2. 带 fresh captcha POST，确认验证码通后仍 405
    print("\n=== 带新鲜 captcha POST ===")
    vp = solve()
    if vp:
        st, allow, acam, txt = raw("POST", {"model":"GLM-5.2","max_tokens":20,"messages":[{"role":"user","content":[{"type":"text","text":"hi"}]}]}, vp)
        print(f"POST(captcha) {st}  allow={allow!r}  acam={acam!r}  body={txt[:200]}")
    else:
        print("captcha solve failed")
