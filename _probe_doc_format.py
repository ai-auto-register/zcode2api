"""按研究文档 §3.2 / §6.2 原版 header + body 复现，排除 header 缺失导致的 405。"""
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
    # 文档 §3.2 原版 header 套件
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
        "User-Agent": "ZCode/unknown",          # 文档原值，非 ZCode/3.0.1
        "HTTP-Referer": "https://zcode.z.ai",
        "X-Title": "Z Code@electron",           # 文档原值
        "Host": "zcode.z.ai",
        "X-Aliyun-Captcha-Verify-Param": vp,
    }
    data = json.dumps(body).encode()
    conn.request("POST", PATH, body=data, headers=headers)
    r = conn.getresponse()
    txt = r.read().decode("utf-8", "ignore")
    conn.close()
    return r.status, txt

if __name__ == "__main__":
    vp = solve()
    if not vp:
        print("captcha failed"); raise SystemExit(1)
    print(f"[verify_param fresh] {vp[:50]}...\n")

    # 文档 §6.2 原版 body：glm-4.7 + 非流式
    for model in ["glm-4.7", "glm-5.2", "glm-5-turbo"]:
        body = {
            "model": model, "max_tokens": 64, "stream": False,
            "messages": [{"role": "user", "content": "只回复两个字：在的"}],
        }
        st, txt = raw(vp, body)
        print(f"--- model={model} (non-stream) ---")
        print(f"   STATUS {st}")
        print(f"   BODY  {txt[:300]}")
        print()
        # verifyParam 可能一次性，每次重新求
        vp = solve()
        if not vp:
            print("   re-solve failed, stop"); break
        print(f"   [re-solved] {vp[:40]}...\n")
