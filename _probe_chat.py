"""一次性探测：求 verifyParam -> 立刻发对话请求，避免参数失效。"""
import subprocess, json, sys, time, urllib.request, urllib.error
import os

def get_fresh_token():
    # 使用 accounts_zcode.json 中刚获取到的 token
    print("[token] 正在从 accounts_zcode.json 获取 zcode_token...")
    accounts_path = r"D:\ptuer\zai2api\accounts_zcode.json"
    if not os.path.exists(accounts_path):
        print("[token] 找不到 accounts_zcode.json")
        return None
    try:
        with open(accounts_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list) and len(data) > 0:
                token = data[0].get("zcode_token")
                if token:
                    print(f"[token] 成功获取! ({len(token)} 字节)")
                    return token
    except Exception as e:
        print(f"[token] 解析 accounts_zcode.json 失败: {e}")
    print("[token] 获取失败!")
    return None

def solve():
    t0 = time.time()
    p = subprocess.run(
        ["node", "solver.js", "11xygtvd", "sgp", "no8xfe"],
        cwd=r"D:\ptuer\zcode2api\captcha_node",
        capture_output=True, text=True, timeout=40,
    )
    for line in p.stdout.splitlines():
        if line.startswith("VERIFY_PARAM="):
            print(f"[solver] OK in {time.time()-t0:.1f}s")
            return line[len("VERIFY_PARAM="):].strip()
    print("[solver] FAILED", p.stderr[-500:])
    return None

def chat(model, verify_param, token):
    url = "https://api.z.ai/api/anthropic/v1/messages"
    body = json.dumps({
        "model": model,
        "max_tokens": 50,
        "stream": False,
        "messages": [{"role": "user", "content": [{"type": "text", "text": "用一个字回答：你好吗"}]}],
    }).encode()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
        "X-ZCode-App-Version": "3.1.1",
        "X-ZCode-Agent": "glm",
        "Referer": "https://zcode.z.ai",
        "User-Agent": "ZCode/3.1.1",
        "X-Aliyun-Captcha-Verify-Param": verify_param,
        "x-api-key": token,
        "X-Platform": "win32-x64",
        "X-Os-Category": "windows",
        "X-Title": "Z Code@electron"
    }
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

if __name__ == "__main__":
    token = get_fresh_token()
    if not token:
        sys.exit(1)
        
    vp = solve()
    if not vp:
        sys.exit(1)
    print(f"[verify_param] {vp[:60]}...")
    for model in ["glm-5.2", "GLM-5.2"]:
        print(f"\n=== model={model} ===")
        st, body = chat(model, vp, token)
        print(f"STATUS: {st}")
        print(f"BODY: {body[:800]}")
        if st == 200:
            print("\n*** 成功！token 可用 ***")
            break
