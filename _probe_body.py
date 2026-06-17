"""穷举 body 结构，定位 3001 parameter error 缺什么。每次新鲜 verifyParam。"""
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

def raw(vp, body):
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
    }
    data = json.dumps(body).encode()
    conn.request("POST", PATH, body=data, headers=headers)
    r = conn.getresponse()
    txt = r.read().decode("utf-8", "ignore")
    conn.close()
    return r.status, txt

CASES = [
    # content 字符串 + 各模型
    ("str content glm-5.2", {"model":"glm-5.2","max_tokens":64,"messages":[{"role":"user","content":"hi"}]}),
    ("str content glm-4.7", {"model":"glm-4.7","max_tokens":64,"messages":[{"role":"user","content":"hi"}]}),
    # content 数组
    ("arr content glm-5.2", {"model":"glm-5.2","max_tokens":64,"messages":[{"role":"user","content":[{"type":"text","text":"hi"}]}]}),
    # 带 system
    ("with system str", {"model":"glm-5.2","max_tokens":64,"system":"You are helpful.","messages":[{"role":"user","content":"hi"}]}),
    ("with system arr", {"model":"glm-5.2","max_tokens":64,"system":[{"type":"text","text":"You are helpful."}],"messages":[{"role":"user","content":"hi"}]}),
    # 大写模型名
    ("UPPER GLM-5.2", {"model":"GLM-5.2","max_tokens":64,"messages":[{"role":"user","content":"hi"}]}),
    # 最小 body
    ("minimal", {"model":"glm-5.2","messages":[{"role":"user","content":"hi"}]}),
    # 带 stream
    ("stream true", {"model":"glm-5.2","max_tokens":64,"stream":True,"messages":[{"role":"user","content":"hi"}]}),
]

if __name__ == "__main__":
    for name, body in CASES:
        vp = solve()
        if not vp:
            print(f"[{name}] solve failed, skip"); continue
        st, txt = raw(vp, body)
        marker = "✅OK" if st == 200 else f"{st}"
        print(f"[{name:22}] {marker}  {txt[:200]}")
        if st == 200:
            print("*** FOUND WORKING COMBO ***")
            print(json.dumps(body, ensure_ascii=False))
            break
        time.sleep(0.5)
