"""ZCode StartPlan 对话接口 —— 可用版（已实测 200）。

破解结论：3012 "method not allowed" 的根因是**系统提示词检测**，
不是 token、不是验证码、不是 host。必须满足：
  1) 端点 StartPlan 路：zcode.z.ai/api/v1/zcode-plan/anthropic/v1/messages
  2) Bearer <zcode_token>（+ x-api-key 同值）
  3) 阿里云验证码头（jsdom solver.js 即可，无需真实浏览器）
  4) body.system 必须含官方 ZCode 前两个 block，**逐字一致**（见 _zcode_system.json）
  5) messages[].content 用对象数组；stream:true
tools / 完整 system / max_tokens 均非必需。两个账号 token 均可用。
"""
import json, subprocess, time, http.client, ssl, os

ACCOUNTS = r"D:\ptuer\zai2api\accounts_zcode.json"
SYSTEM   = r"D:\ptuer\zcode2api\_zcode_system.json"   # 官方前两个 system block（逐字）
PATH     = "/api/v1/zcode-plan/anthropic/v1/messages"


def get_token():
    return json.load(open(ACCOUNTS, encoding="utf-8"))[0]["zcode_token"]


def solve(retries=3):
    """jsdom 解阿里云无痕验证码（单次有效）。"""
    for _ in range(retries):
        p = subprocess.run(["node", "solver.js", "11xygtvd", "sgp", "no8xfe"],
                           cwd=r"D:\ptuer\zcode2api\captcha_node",
                           capture_output=True, text=True, timeout=50)
        for line in p.stdout.splitlines():
            if line.startswith("VERIFY_PARAM="):
                return line[len("VERIFY_PARAM="):].strip()
        time.sleep(1)
    return None


def chat(token, vp, user_text, model="GLM-5.2"):
    system = json.load(open(SYSTEM, encoding="utf-8"))   # ★ 关键：官方系统提示词
    body = {
        "model": model, "max_tokens": 1024, "stream": True,
        "system": system,
        "messages": [{"role": "user", "content": [{"type": "text", "text": user_text}]}],
    }
    headers = {
        "anthropic-version": "2023-06-01",
        "authorization": f"Bearer {token}",
        "x-api-key": token,
        "content-type": "application/json",
        "http-referer": "https://zcode.z.ai",
        "user-agent": "ZCode/3.1.1",
        "x-aliyun-captcha-verify-param": vp,
        "x-aliyun-captcha-verify-region": "sgp",
        "Host": "zcode.z.ai",
        "Accept": "text/event-stream",
    }
    c = http.client.HTTPSConnection("zcode.z.ai", timeout=90, context=ssl.create_default_context())
    c.request("POST", PATH, body=json.dumps(body).encode(), headers=headers)
    r = c.getresponse(); txt = r.read().decode("utf-8", "ignore"); c.close()
    return r.status, txt


def parse_sse_text(sse):
    """从 SSE 流提取拼接的文本。"""
    out = []
    for line in sse.splitlines():
        if line.startswith("data:"):
            try:
                ev = json.loads(line[5:].strip())
                if ev.get("type") == "content_block_delta":
                    out.append(ev["delta"].get("text", ""))
            except Exception:
                pass
    return "".join(out)


if __name__ == "__main__":
    token = get_token()
    vp = solve()
    if not vp:
        print("验证码求解失败"); raise SystemExit(1)
    st, sse = chat(token, vp, "用一句话介绍你自己")
    print("STATUS:", st)
    if st == 200:
        print("回复:", parse_sse_text(sse) or sse[:300])
        print("\n*** 接口可用 ***")
    else:
        print("BODY:", sse[:400])
