// 用系统 Chrome（真实指纹）跑阿里云无痕验证，产出 verify_param。
// 对比 jsdom 桩：真实 canvas/webgl/字体/Worker → 服务端验证更可能通过。
// 用法: node solver_pw.js [scene] [region] [prefix]   环境变量 HEADLESS=1 走无头
const { chromium } = require('playwright-core');
const http = require('http');

const SCENE  = process.argv[2] || '11xygtvd';
const REGION = process.argv[3] || 'sgp';
const PREFIX = process.argv[4] || 'no8xfe';
const HEADLESS = process.env.HEADLESS === '1';

const HTML = `<!DOCTYPE html><html><head><meta charset="utf-8">
<script src="https://o.alicdn.com/captcha-frontend/aliyunCaptcha/AliyunCaptcha.js"></script>
</head><body><div id="cap"></div><button id="btn" style="display:none"></button>
<script>
function boot(){
  if (typeof window.initAliyunCaptcha !== 'function') { setTimeout(boot, 50); return; }
  window.initAliyunCaptcha({
    SceneId: ${JSON.stringify(SCENE)}, mode:'popup', region: ${JSON.stringify(REGION)},
    prefix: ${JSON.stringify(PREFIX)}, element:'#cap', button:'#btn',
    captchaLogoImg:'', showErrorTip:false, language:'cn',
    getInstance:(inst)=>{ window.__i=inst;
      try{ (inst.startTracelessVerification||inst.show).call(inst); }
      catch(e){ try{document.getElementById('btn').click();}catch(_){} } },
    success:(p)=>{ window.__submitParam(String(p)); },
    fail:(e)=>{ window.__submitParam('FAIL:'+JSON.stringify(e||{})); },
    onError:(e)=>{ window.__submitParam('ERR:'+JSON.stringify(e||{})); },
  });
}
window.addEventListener('DOMContentLoaded', boot);
</script></body></html>`;

(async () => {
  // 本地服务托管验证页（localhost origin，阿里 SDK 可用）
  const srv = http.createServer((req, res) => {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(HTML);
  });
  await new Promise(r => srv.listen(0, '127.0.0.1', r));
  const port = srv.address().port;

  let browser;
  try {
    browser = await chromium.launch({
      channel: 'chrome', headless: HEADLESS,
      args: ['--disable-blink-features=AutomationControlled', '--no-sandbox', '--no-first-run'],
      ignoreDefaultArgs: ['--enable-automation'],
    });
  } catch (e) {
    console.error('LAUNCH_FAIL ' + e.message); process.exit(5);
  }

  const ctx = await browser.newContext({ locale: 'zh-CN' });
  const page = await ctx.newPage();
  // 去掉 navigator.webdriver
  await page.addInitScript(() => { Object.defineProperty(navigator, 'webdriver', { get: () => undefined }); });

  const got = new Promise((resolve) => { page.exposeFunction('__submitParam', (p) => resolve(p)); });

  await page.goto(`http://127.0.0.1:${port}/`, { waitUntil: 'domcontentloaded', timeout: 30000 });

  const result = await Promise.race([
    got,
    new Promise((r) => setTimeout(() => r('TIMEOUT'), 30000)),
  ]);

  await browser.close().catch(() => {});
  srv.close();

  if (result && result.startsWith('eyJ')) { console.log('VERIFY_PARAM=' + result); process.exit(0); }
  console.error('NO_PARAM: ' + String(result).slice(0, 200)); process.exit(2);
})().catch(e => { console.error('FATAL ' + e.message); process.exit(3); });
