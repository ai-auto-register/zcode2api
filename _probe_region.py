"""补 X-Aliyun-Captcha-Verify-Region 头，试数组 content。"""
import subprocess, json, time, http.client, ssl

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

def raw(vp, body, extra_headers=None):
    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection("zcode.z.ai", timeout=60, context=ctx)
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
        "User-Agent": "ZCode/unknown",
        "HTTP-Referer": "https://zcode.z.ai",
        "X-Title": "Z Code@electron",
        "Host": "zcode.z.ai",
        "X-Aliyun-Captcha-Verify-Param": vp,
        "X-Aliyun-Captcha-Verify-Region": "sgp",
    }
    if extra_headers:
        headers.update(extra_headers)
    data = json.dumps(body).encode()
    conn.request("POST", PATH, body=data, headers=headers)
    r = conn.getresponse()
    txt = r.read().decode("utf-8", "ignore")
    conn.close()
    return r.status, txt

# 解码 verifyParam 看里面有没有 region 信息
def decode_vp(vp):
    import base64
    try:
        return json.loads(base64.b64decode(vp))
    except Exception:
        return {}

if __name__ == "__main__":
    vp = solve()
    if not vp:
        print("solve failed"); raise SystemExit(1)
    print(f"[verify_param fresh] {vp[:60]}...")
    print(f"[decoded] {decode_vp(vp)}\n")

    CASES = [
        ("arr+region", {"model":"glm-5.2","max_tokens":64,"messages":[{"role":"user","content":[{"type":"text","text":"hi"}]}]}),
    ]
    for name, body in CASES:
        st, txt = raw(vp, body)
        print(f"[{name}] STATUS {st}")
        print(f"   BODY {txt[:400]}")
        if st != 200:
            vp = solve()
            if vp:
                print(f"\n   [re-solved] {vp[:40]}...")
