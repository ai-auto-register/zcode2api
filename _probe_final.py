"""最后一轮：精确组合测试，含 SSE 流式读取。"""
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

def raw(vp, body, accept=None):
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
    if accept:
        headers["Accept"] = accept
    data = json.dumps(body).encode()
    conn.request("POST", PATH, body=data, headers=headers)
    r = conn.getresponse()
    txt = r.read().decode("utf-8", "ignore")
    ct = r.getheader("content-type", "")
    conn.close()
    return r.status, txt, ct

CASES = [
    # 流式 + 数组 content
    ("stream+arr", {"model":"glm-5.2","max_tokens":64,"stream":True,
                    "messages":[{"role":"user","content":[{"type":"text","text":"hi"}]}]}, "text/event-stream"),
    # 流式 + 字符串 content
    ("stream+str", {"model":"glm-5.2","max_tokens":64,"stream":True,
                    "messages":[{"role":"user","content":"hi"}]}, "text/event-stream"),
    # 完全 Anthropic 官方 SDK 形态
    ("sdk-form", {"model":"glm-5.2","max_tokens":1024,
                  "messages":[{"role":"user","content":[{"type":"text","text":"Say hello"}]}]}, None),
    # 带 metadata
    ("with-meta", {"model":"glm-5.2","max_tokens":64,
                   "messages":[{"role":"user","content":"hi"}],
                   "metadata":{"user_id":"test"}}, None),
    # 带 temperature
    ("with-temp", {"model":"glm-5.2","max_tokens":64,"temperature":0.7,
                   "messages":[{"role":"user","content":"hi"}]}, None),
    # 多轮
    ("multi-turn", {"model":"glm-5.2","max_tokens":64,
                    "messages":[{"role":"user","content":"a"},{"role":"assistant","content":"b"},{"role":"user","content":"c"}]}, None),
]

if __name__ == "__main__":
    for name, body, accept in CASES:
        vp = solve()
        if not vp:
            print(f"[{name:14}] solve-fail"); continue
        st, txt, ct = raw(vp, body, accept)
        flag = "✅OK✅" if st == 200 else str(st)
        print(f"[{name:14}] {flag}  ct={ct[:30]}  body={txt[:180]}")
        if st == 200:
            print("*** SUCCESS ***")
            print(json.dumps(body, ensure_ascii=False))
            break
        time.sleep(0.3)
