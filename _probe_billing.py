"""探查 zcode-plan billing/balance/usage 三个接口的真实返回结构，
确认 quota.py 读的字段名是否匹配，以及 total/remaining 是不是 0。
"""
import json, http.client, ssl, base64

token = json.load(open(r"D:\ptuer\zai2api\accounts_zcode.json", encoding="utf-8"))[0]["zcode_token"]
uid = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))["user_id"][:8]
print("[account]", uid)

BASE = "zcode.z.ai"
PATHS = ["/api/v1/zcode-plan/billing/current", "/api/v1/zcode-plan/billing/balance", "/api/v1/zcode-plan/usage"]

headers = {
    "authorization": f"Bearer {token}",
    "x-api-key": token,
    "content-type": "application/json",
    "user-agent": "ZCode/3.0.1",
}

ctx = ssl.create_default_context()
for path in PATHS:
    c = http.client.HTTPSConnection(BASE, timeout=20, context=ctx)
    c.request("GET", path, headers=headers)
    r = c.getresponse()
    txt = r.read().decode("utf-8", "ignore")
    c.close()
    print(f"\n===== GET {path} -> {r.status} =====")
    try:
        data = json.loads(txt)
        print(json.dumps(data, ensure_ascii=False, indent=2)[:1500])
    except Exception:
        print(txt[:800])
