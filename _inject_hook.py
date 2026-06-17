# 给 zcode.cjs 顶部注入 globalThis.fetch 日志 hook（备份 + 可还原）
import os

GLM_DIR = r"D:\Users\Admin\AppData\Local\Programs\ZCode\resources\glm"
path = os.path.join(GLM_DIR, "zcode.cjs")
bak  = os.path.join(GLM_DIR, "zcode.cjs.orig")
LOG  = r"D:\ptuer\zcode2api\_app_capture.log"

# hook：CommonJS，捕获对话端点请求的 URL/headers/body 与响应码
HOOK = (
    'try{(function(){'
    'var fs=require("fs");'
    'var LOG=' + repr(LOG).replace("'", '"') + ';'
    'function ser(h){try{if(!h)return null;'
    'if(typeof h.forEach==="function"&&typeof h.entries==="function"){var o={};h.forEach(function(v,k){o[k]=v});return o}'
    'return h}catch(e){return String(h)}}'
    'var of=globalThis.fetch;'
    'if(of&&!globalThis.__cap){globalThis.__cap=1;'
    'globalThis.fetch=function(input,init){'
    'var url="";try{url=String(input&&input.url?input.url:input)}catch(e){}'
    'var hit=url.indexOf("/v1/messages")>=0||url.indexOf("anthropic")>=0||url.indexOf("zcode-plan")>=0;'
    'if(hit){try{'
    'var hdr=ser(init&&init.headers)||(input&&input.headers?ser(input.headers):null);'
    'var body=init&&init.body;if(typeof body!=="string")body="[non-string]";'
    'fs.appendFileSync(LOG,"\\n===== REQ =====\\nURL: "+url+"\\nHEADERS: "+JSON.stringify(hdr)+"\\nBODY: "+body+"\\n")'
    '}catch(e){}}'
    'var p=of.apply(this,arguments);'
    'if(hit){try{p.then(function(res){try{fs.appendFileSync(LOG,"RESP STATUS: "+res.status+"\\n")}catch(e){}return res}).catch(function(){})}catch(e){}}'
    'return p}}})()}catch(e){}'
)

data = open(path, "r", encoding="utf-8", errors="surrogatepass", newline="").read()

if not os.path.exists(bak):
    open(bak, "w", encoding="utf-8", errors="surrogatepass", newline="").write(data)
    print("[backup] zcode.cjs.orig 已创建")
else:
    print("[backup] 已存在，跳过")

if "globalThis.__cap" in data[:6000]:
    print("[hook] 已注入过，跳过")
else:
    nl = data.index("\n") + 1   # shebang 之后
    out = data[:nl] + HOOK + "\n" + data[nl:]
    open(path, "w", encoding="utf-8", errors="surrogatepass", newline="").write(out)
    print("[hook] 已注入 zcode.cjs 顶部 (+%d 字节)" % len(HOOK))

print("[log] 抓包将写入:", LOG)
