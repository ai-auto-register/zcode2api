"""系统性网格测试：定位 3001 parameter error 的触发字段。
每个变体用新鲜 verifyParam，字符串 content（已知走 400 分支）。
"""
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
        "X-Aliyun-Captcha-Verify-Region": "sgp",
    }
    data = json.dumps(body).encode()
    conn.request("POST", PATH, body=data, headers=headers)
    r = conn.getresponse()
    txt = r.read().decode("utf-8", "ignore")
    conn.close()
    return r.status, txt

def base_body(model):
    return {"model": model, "max_tokens": 64, "messages":[{"role":"user","content":"hi"}]}

MODELS = ["glm-5.2","GLM-5.2","glm-5-turbo","GLM-5-Turbo","glm-turbo",
          "glm-4.7","glm-5.1","glm-4.6","glm-4.5","glm-4-flash"]

if __name__ == "__main__":
    print("=== 网格1：模型名（字符串 content, 非流式）===")
    for m in MODELS:
        vp = solve()
        if not vp:
            print(f"  {m:14} solve-fail"); continue
        st, txt = raw(vp, base_body(m))
        flag = "OK✅✅✅" if st == 200 else str(st)
        print(f"  {m:14} -> {flag}  {txt[:150]}")
        if st == 200:
            print("*** WORKING MODEL:", m); break
        time.sleep(0.3)
