"""探测 zcode.z.ai 真实可用的对话端点路径。"""
import json, time, http.client, ssl

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiNzRiOGIxMzAtNDM2OC00OWVhLWFjZTEtMzg4YTJmOGRmYjBlIiwic3ViIjoiNzRiOGIxMzAtNDM2OC00OWVhLWFjZTEtMzg4YTJmOGRmYjBlIiwiaWF0IjoxNzgxNjE5MjgzfQ.GLIjAsmbbBuo0jX2S4-9Dh-5FMRbxAaQ6b5okq3yQN0"

def raw(method, path, body=None):
    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection("zcode.z.ai", timeout=20, context=ctx)
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
        "X-ZCode-App-Version": "3.0.1",
        "X-ZCode-Agent": "glm",
        "User-Agent": "ZCode/3.0.1",
        "Host": "zcode.z.ai",
    }
    data = json.dumps(body).encode() if body is not None else None
    conn.request(method, path, body=data, headers=headers)
    r = conn.getresponse()
    txt = r.read().decode("utf-8", "ignore")
    conn.close()
    return r.status, txt[:200]

candidates = [
    # Anthropic 风格变体
    "/api/v1/messages",
    "/api/v1/anthropic/v1/messages",
    "/api/anthropic/v1/messages",
    "/anthropic/v1/messages",
    "/v1/messages",
    "/api/v1/zcode-plan/messages",
    # OpenAI 风格
    "/api/v1/chat/completions",
    "/api/v1/zcode-plan/chat/completions",
    "/v1/chat/completions",
    # zcode-plan 下其它子路径
    "/api/v1/zcode-plan/anthropic/messages",
    "/api/v1/zcode-plan/v1/messages",
    # 看看 plan 根返回啥
    "/api/v1/zcode-plan",
    "/api/v1/zcode-plan/",
]

print("=== 不带 captcha，看路由是否存在（404=不存在，其它=存在）===")
for p in candidates:
    try:
        st, txt = raw("POST", p, {"model":"GLM-5.2","max_tokens":10,"messages":[{"role":"user","content":"hi"}]})
        flag = "EXISTS" if st != 404 else "404"
        print(f"[{flag:6}] {st}  {p}")
        if st not in (404,):
            print(f"           body: {txt[:150]}")
    except Exception as e:
        print(f"[ERR]    {p}  {e}")
    time.sleep(0.25)
