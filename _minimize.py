# 最小化测试：定位 zcode-plan 对话接口 200 的最小必要条件
import json, http.client, ssl, subprocess, copy, time, base64

APP_TOKEN = open(r"D:\ptuer\zcode2api\_app_token.txt").read().strip()
MY_TOKEN  = json.load(open(r"D:\ptuer\zai2api\accounts_zcode.json"))[0]["zcode_token"]
BODY      = json.load(open(r"D:\ptuer\zcode2api\_app_body.json", encoding="utf-8"))

def uid(t):
    return json.loads(base64.urlsafe_b64decode(t.split('.')[1]+'=='))['user_id'][:8]

def solve(retries=3):
    for _ in range(retries):
        p = subprocess.run(["node", "captcha_node/solver_pw.js", "11xygtvd", "sgp", "no8xfe"],
                           cwd=r"D:\ptuer\zcode2api", capture_output=True, text=True, timeout=70)
        for line in p.stdout.splitlines():
            if line.startswith("VERIFY_PARAM="):
                return line[len("VERIFY_PARAM="):].strip()
        time.sleep(1)
    return None

def call(token, body, vp):
    h = {'anthropic-version':'2023-06-01','authorization':f'Bearer {token}','content-type':'application/json',
         'http-referer':'https://zcode.z.ai','user-agent':'ZCode/3.1.1 ai-sdk/provider-utils/4.0.27 runtime/node.js/24',
         'x-aliyun-captcha-verify-param':vp,'x-aliyun-captcha-verify-region':'sgp','x-api-key':token,
         'x-title':'Z Code@electron','x-zcode-agent':'glm','x-zcode-app-version':'3.1.1',
         'Host':'zcode.z.ai','Accept':'text/event-stream'}
    c = http.client.HTTPSConnection('zcode.z.ai', timeout=90, context=ssl.create_default_context())
    c.request('POST', '/api/v1/zcode-plan/anthropic/v1/messages', body=json.dumps(body).encode(), headers=h)
    r = c.getresponse(); txt = r.read().decode('utf-8','ignore'); c.close()
    return r.status, txt[:120].replace('\n',' ')

def run(name, token, body):
    vp = solve()
    if not vp:
        print(f"[{name}] solve-fail"); return
    st, txt = call(token, body, vp)
    flag = "*** 200 OK ***" if st == 200 else f"FAIL {st}"
    print(f"[{name}] token={uid(token)} {flag}  {txt}")

# 变体
no_tools = copy.deepcopy(BODY); no_tools.pop('tools',None); no_tools.pop('tool_choice',None)
sys2 = copy.deepcopy(BODY); sys2['system'] = BODY['system'][:2]
sys2_notools = copy.deepcopy(sys2); sys2_notools.pop('tools',None); sys2_notools.pop('tool_choice',None)
minimal = {'model':'GLM-5.2','max_tokens':64,'stream':True,
           'messages':[{'role':'user','content':[{'type':'text','text':'hi'}]}]}

print("=== 最小必要条件定位 ===")
run("MY_TOKEN + 完整body   ", MY_TOKEN, BODY)        # 我的账号能否通
run("APP + 去tools         ", APP_TOKEN, no_tools)   # tools 是否必需
run("APP + 仅2个system     ", APP_TOKEN, sys2)       # system 是否需完整
run("APP + 2sys+去tools    ", APP_TOKEN, sys2_notools)
run("APP + 极简body        ", APP_TOKEN, minimal)    # 纯 minimal
