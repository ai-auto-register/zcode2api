# 第二轮：system 是"存在即可"还是"内容必须匹配官方"？
import json, http.client, ssl, subprocess, time, base64

APP_TOKEN = open(r"D:\ptuer\zcode2api\_app_token.txt").read().strip()
MY_TOKEN  = json.load(open(r"D:\ptuer\zai2api\accounts_zcode.json"))[0]["zcode_token"]
BODY      = json.load(open(r"D:\ptuer\zcode2api\_app_body.json", encoding="utf-8"))
SYS_FULL  = BODY["system"]                       # 官方完整 system
SYS_B1    = [SYS_FULL[0]]                         # 仅"You are ZCode, an interactive coding agent"

def solve(retries=3):
    for _ in range(retries):
        p = subprocess.run(["node","captcha_node/solver_pw.js","11xygtvd","sgp","no8xfe"],
                           cwd=r"D:\ptuer\zcode2api", capture_output=True, text=True, timeout=70)
        for line in p.stdout.splitlines():
            if line.startswith("VERIFY_PARAM="):
                return line[len("VERIFY_PARAM="):].strip()
        time.sleep(1)
    return None

def call(token, system, vp):
    body = {'model':'GLM-5.2','max_tokens':64,'stream':True,
            'messages':[{'role':'user','content':[{'type':'text','text':'hi'}]}]}
    if system is not None:
        body['system'] = system
    h = {'anthropic-version':'2023-06-01','authorization':f'Bearer {token}','content-type':'application/json',
         'http-referer':'https://zcode.z.ai','user-agent':'ZCode/3.1.1 ai-sdk/provider-utils/4.0.27 runtime/node.js/24',
         'x-aliyun-captcha-verify-param':vp,'x-aliyun-captcha-verify-region':'sgp','x-api-key':token,
         'x-title':'Z Code@electron','x-zcode-agent':'glm','x-zcode-app-version':'3.1.1',
         'Host':'zcode.z.ai','Accept':'text/event-stream'}
    c = http.client.HTTPSConnection('zcode.z.ai', timeout=90, context=ssl.create_default_context())
    c.request('POST','/api/v1/zcode-plan/anthropic/v1/messages', body=json.dumps(body).encode(), headers=h)
    r = c.getresponse(); txt = r.read().decode('utf-8','ignore'); c.close()
    return r.status, txt[:90].replace('\n',' ')

def run(name, token, system):
    vp = solve()
    if not vp: print(f"[{name}] solve-fail"); return
    st, txt = call(token, system, vp)
    print(f"[{name}] {'200 OK' if st==200 else 'FAIL '+str(st)}  {txt if st!=200 else ''}")

print("=== 第二轮：system 内容检测粒度 ===")
run("假system(generic)  ", APP_TOKEN, [{'type':'text','text':'You are a helpful assistant.'}])
run("仅第一句(ZCode身份) ", APP_TOKEN, SYS_B1)
run("MY_TOKEN+仅第一句   ", MY_TOKEN, SYS_B1)
run("system=空数组       ", APP_TOKEN, [])
