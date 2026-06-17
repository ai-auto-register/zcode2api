"""用用户给的 token（74b8b130）探查 billing/balance/usage 真实返回，
对比 quota.py 的字段映射，确认为什么后台没有绿色额度条。
"""
import json, http.client, ssl, base64

token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiNzRiOGIxMzAtNDM2OC00OWVhLWFjZTEtMzg4YTJmOGRmYjBlIiwic3ViIjoiNzRiOGIxMzAtNDM2OC00OWVhLWFjZTEtMzg4YTJmOGRmYjBlIiwiaWF0IjoxNzgxNjUxMTI1fQ.oYiicK_JjLAm8xT5FMkUsQ2ZreRb-l9nywUGnj1YGQg"
uid = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))["user_id"][:8]
print("[account]", uid)

BASE = "zcode.z.ai"
PATHS = ["/api/v1/zcode-plan/billing/current", "/api/v1/zcode-plan/billing/balance", "/api/v1/zcode-plan/usage"]
headers = {"authorization": f"Bearer {token}", "x-api-key": token, "content-type": "application/json",
           "user-agent": "ZCode/3.0.1", "anthropic-version": "2023-06-01",
           "X-ZCode-App-Version": "3.0.1", "X-ZCode-Agent": "glm", "HTTP-Referer": "https://zcode.z.ai/"}

ctx = ssl.create_default_context()


def http_get(path, retries=3):
    for i in range(retries):
        try:
            c = http.client.HTTPSConnection(BASE, timeout=20, context=ctx)
            c.request("GET", path, headers=headers)
            r = c.getresponse()
            txt = r.read().decode("utf-8", "ignore")
            c.close()
            return r.status, txt
        except Exception as e:
            print(f"  [retry {i+1}/{retries}] {type(e).__name__}: {e}")
            import time; time.sleep(1)
    return None, ""


for path in PATHS:
    st, txt = http_get(path)
    print(f"\n===== GET {path} -> {st} =====")
    try:
        data = json.loads(txt)
        print(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception:
        print(txt[:800])

# 模拟 quota.py 的 balance 映射
print("\n\n===== 模拟 quota.py balance 映射 =====")
st, txt = http_get("/api/v1/zcode-plan/billing/balance")
try:
    data = json.loads(txt)
except Exception:
    data = {}
quota_map = {}
for bal in (data.get("data") or {}).get("balances") or []:
    name = bal.get("show_name") or bal.get("model") or "model"
    quota_map[name] = {"total": bal.get("total_units"), "used": bal.get("used_units"),
                       "remaining": bal.get("remaining_units"), "expires_at": bal.get("expires_at")}
print("quota_map:", json.dumps(quota_map, ensure_ascii=False, indent=2))
print("has_data 判定:", bool(quota_map))
