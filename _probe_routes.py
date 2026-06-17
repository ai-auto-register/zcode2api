"""探测：新鲜 verifyParam 下，试不同端点/方法，定位 405 根因。"""
import subprocess, json, sys, time, urllib.request, urllib.error

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiNzRiOGIxMzAtNDM2OC00OWVhLWFjZTEtMzg4YTJmOGRmYjBlIiwic3ViIjoiNzRiOGIxMzAtNDM2OC00OWVhLWFjZTEtMzg4YTJmOGRmYjBlIiwiaWF0IjoxNzgxNjE5MjgzfQ.GLIjAsmbbBuo0jX2S4-9Dh-5FMRbxAaQ6b5okq3yQN0"

def solve():
    p = subprocess.run(
        ["node", "solver.js", "11xygtvd", "sgp", "no8xfe"],
        cwd=r"D:\ptuer\zcode2api\captcha_node",
        capture_output=True, text=True, timeout=40,
    )
    for line in p.stdout.splitlines():
        if line.startswith("VERIFY_PARAM="):
            return line[len("VERIFY_PARAM="):].strip()
    return None

def req(method, url, verify_param=None, body=None):
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
        "X-ZCode-App-Version": "3.0.1",
        "X-ZCode-Agent": "glm",
        "HTTP-Referer": "https://zcode.z.ai/",
        "User-Agent": "ZCode/3.0.1",
    }
    if verify_param:
        headers["X-Aliyun-Captcha-Verify-Param"] = verify_param
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, dict(resp.headers), resp.read().decode()[:400]
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()[:400]
    except Exception as e:
        return -1, {}, str(e)[:200]

if __name__ == "__main__":
    vp = solve()
    print(f"[verify_param fresh] {vp[:50]}...\n")

    base = "https://zcode.z.ai/api/v1"
    candidates = [
        # 当前项目用的端点
        ("POST", f"{base}/zcode-plan/anthropic/v1/messages", {"model":"glm-5.2","max_tokens":20,"messages":[{"role":"user","content":[{"type":"text","text":"hi"}]}]}),
        # 标准化路径变体
        ("POST", f"{base}/zcode-plan/messages", {"model":"glm-5.2","max_tokens":20,"messages":[{"role":"user","content":"hi"}]}),
        ("POST", f"{base}/zcode-plan/chat/completions", {"model":"glm-5.2","max_tokens":20,"messages":[{"role":"user","content":"hi"}]}),
        # OpenAI 风格
        ("POST", f"{base}/zcode-plan/v1/chat/completions", {"model":"glm-5.2","max_tokens":20,"messages":[{"role":"user","content":"hi"}]}),
        # 探测可用路由（OPTIONS/GET）
        ("OPTIONS", f"{base}/zcode-plan/anthropic/v1/messages", None),
    ]
    for method, url, body in candidates:
        st, hdrs, txt = req(method, url, vp if body is not None else None, body)
        allow = hdrs.get("Allow") or hdrs.get("allow") or ""
        print(f"[{method}] {url.replace(base,'')}")
        print(f"   -> {st}  allow={allow!r}  body={txt[:200]}")
        print()
