"""StartPlan 路对话探测：新 token（accounts_zcode.json）+ zcode.z.ai/zcode-plan/anthropic。

修正 _probe_chat.py 的 host 错误：
  - 错误：api.z.ai/api/anthropic + zcode_token  → 401（该路需 finalToken）
  - 正确：zcode.z.ai/api/v1/zcode-plan/anthropic + Bearer zcode_token（与 billing 同源同 token）
依据研究文档 §3.2 / §3.4。验证码 param 单次有效，故每个请求前重新求解。
"""
import subprocess, json, time, http.client, ssl, os

ACCOUNTS = r"D:\ptuer\zai2api\accounts_zcode.json"
PATH = "/api/v1/zcode-plan/anthropic/v1/messages"


def get_fresh_token():
    """从 accounts_zcode.json 读取最新激活的 zcode_token。"""
    if not os.path.exists(ACCOUNTS):
        print(f"[token] 找不到 {ACCOUNTS}")
        return None
    with open(ACCOUNTS, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list) and data:
        tok = data[0].get("zcode_token")
        if tok:
            print(f"[token] OK ({len(tok)} 字节) user={data[0].get('user_id', '?')[:8]}")
            return tok
    print("[token] 获取失败")
    return None


def solve(retries=4):
    """求 Aliyun 验证码 verify_param（单次有效）。"""
    for _ in range(retries):
        p = subprocess.run(
            ["node", "solver.js", "11xygtvd", "sgp", "no8xfe"],
            cwd=r"D:\ptuer\zcode2api\captcha_node",
            capture_output=True, text=True, timeout=40,
        )
        for line in p.stdout.splitlines():
            if line.startswith("VERIFY_PARAM="):
                return line[len("VERIFY_PARAM="):].strip()
        time.sleep(1)
    return None


def chat(token, vp, body):
    """打 StartPlan 对话接口，返回 (status, text)。"""
    conn = http.client.HTTPSConnection("zcode.z.ai", timeout=60, context=ssl.create_default_context())
    headers = {
        "Authorization": f"Bearer {token}",
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
        "User-Agent": "ZCode/unknown",
        "HTTP-Referer": "https://zcode.z.ai",
        "X-Title": "Z Code@electron",
        "Host": "zcode.z.ai",
        "X-Aliyun-Captcha-Verify-Param": vp,
        "X-Aliyun-Captcha-Verify-Region": "sgp",
    }
    conn.request("POST", PATH, body=json.dumps(body).encode(), headers=headers)
    r = conn.getresponse()
    txt = r.read().decode("utf-8", "ignore")
    conn.close()
    return r.status, txt


if __name__ == "__main__":
    token = get_fresh_token()
    if not token:
        raise SystemExit(1)

    # 计划授权模型：GLM-5.2 / GLM-5-Turbo（见 plan.entitlements）；glm-4.7 为文档默认兜底
    for model in ["glm-5.2", "GLM-5.2", "glm-5-turbo", "glm-4.7"]:
        vp = solve()
        if not vp:
            print(f"[{model:11}] solve-fail")
            continue
        body = {
            "model": model, "max_tokens": 64, "stream": False,
            "messages": [{"role": "user", "content": "只回复两个字：在的"}],
        }
        st, txt = chat(token, vp, body)
        flag = "✅ OK" if st == 200 else str(st)
        print(f"[{model:11}] {flag}  {txt[:240]}")
        if st == 200:
            print("\n*** 成功！StartPlan 对话接口可用 ***")
            break
        time.sleep(0.4)
