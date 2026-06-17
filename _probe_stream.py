"""探测 405 根因：试 stream:true、不同 model、GET。"""
import subprocess, json, sys, time, urllib.request, urllib.error

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiNzRiOGIxMzAtNDM2OC00OWVhLWFjZTEtMzg4YTJmOGRmYjBlIiwic3ViIjoiNzRiOGIxMzAtNDM2OC00OWVhLWFjZTEtMzg4YTJmOGRmYjBlIiwiaWF0IjoxNzgxNjE5MjgzfQ.GLIjAsmbbBuo0jX2S4-9Dh-5FMRbxAaQ6b5okq3yQN0"
URL = "https://zcode.z.ai/api/v1/zcode-plan/anthropic/v1/messages"

def solve(retries=4):
    for _ in range(retries):
        p = subprocess.run(["node", "solver.js", "11xygtvd", "sgp", "no8xfe"],
            cwd=r"D:\ptuer\zcode2api\captcha_node", capture_output=True, text=True, timeout=40)
        for line in p.stdout.splitlines():
            if line.startswith("VERIFY_PARAM="):
                return line[len("VERIFY_PARAM="):].strip()
        time.sleep(1)
    return None

def base_headers(vp):
    return {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
        "X-ZCode-App-Version": "3.0.1",
        "X-ZCode-Agent": "glm",
        "HTTP-Referer": "https://zcode.z.ai/",
        "User-Agent": "ZCode/3.0.1",
        "X-Aliyun-Captcha-Verify-Param": vp,
    }

def post(vp, payload):
    data = json.dumps(payload).encode()
    r = urllib.request.Request(URL, data=data, headers=base_headers(vp), method="POST")
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, resp.read().decode()[:500]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:500]

if __name__ == "__main__":
    vp = solve()
    if not vp:
        print("求解失败，退出"); sys.exit(1)
    print(f"[verify_param fresh] {vp[:50]}...\n")

    cases = [
        ("stream=true lowercase", {"model":"glm-5.2","max_tokens":20,"stream":True,"messages":[{"role":"user","content":[{"type":"text","text":"hi"}]}]}),
        ("stream=true GLM-5-Turbo", {"model":"glm-5-turbo","max_tokens":20,"stream":True,"messages":[{"role":"user","content":[{"type":"text","text":"hi"}]}]}),
        ("no X-ZCode-Agent header variants handled separately", None),
    ]
    for name, payload in cases:
        if payload is None:
            continue
        st, body = post(vp, payload)
        print(f"--- {name} ---")
        print(f"   STATUS {st}")
        print(f"   BODY  {body[:400]}")
        print()
        # verifyParam 可能一次性，每次重新求
        vp = solve()
        if not vp:
            print("   [re-solve failed] 停止"); break
        print(f"   [re-solved] {vp[:40]}...\n")
