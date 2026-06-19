'use strict';

// 测试用 NVC (AWSC) 方式求解 verifyParam，看能否拿到含 securityToken 的完整串。
// 用法: node test_nvc.js [appkey] [scene] [region]
// appkey 先用 configs 的 prefix 值试

require('global-agent/bootstrap');

const { JSDOM, VirtualConsole } = require('jsdom');
const http = require('http');
const https = require('https');

const APPKEY = process.argv[2] || 'no8xfe';
const SCENE = process.argv[3] || '11xygtvd';
const REGION = process.argv[4] || 'sgp';
const UA = process.env.ZCODE_UA || 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36';

function proxyViaPython(url, method, reqUrl, headers, body) {
  // 直连模式（不走 Python rnet），用 node https 发请求
  return new Promise((resolve, reject) => {
    const u = new URL(reqUrl);
    const lib = u.protocol === 'https:' ? https : http;
    const req = lib.request({
      hostname: u.hostname,
      port: u.port,
      path: u.pathname + u.search,
      method,
      headers: headers || {},
    }, (res) => {
      const chunks = [];
      res.on('data', (c) => chunks.push(c));
      res.on('end', () => {
        resolve({ status: res.statusCode, headers: res.headers, body: Buffer.concat(chunks) });
      });
    });
    req.on('error', (e) => reject(e));
    req.setTimeout(30000, () => req.destroy(new Error('timeout')));
    if (body) req.write(body);
    req.end();
  });
}

const html = `<!DOCTYPE html><html><head>
<script src="https://g.alicdn.com/AWSC/AWSC/awsc.js"></script>
</head><body><div id="nc"></div></body></html>`;

const vc = new VirtualConsole();
vc.on('jsdomError', (e) => console.error('[jsdomError]', e.message));
vc.on('error', (...a) => console.error('[console.error]', ...a));
vc.on('log', (...a) => console.log('[console.log]', ...a));

const dom = new JSDOM(html, {
  url: 'https://zcode.z.ai/',
  runScripts: 'dangerously',
  resources: 'usable',
  pretendToBeVisual: true,
  virtualConsole: vc,
  beforeParse(window) {
    try {
      Object.defineProperty(window.navigator, 'userAgent', { get: () => UA, configurable: true });
    } catch (_) {}
    window.matchMedia = () => ({ matches: false, media: '', onchange: null, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}, dispatchEvent() { return false; } });
    const proto = window.HTMLCanvasElement.prototype;
    proto.getContext = function (type) {
      if (/webgl/i.test(type)) return { canvas: this, getParameter: () => 'Intel', getExtension: () => null, getSupportedExtensions: () => ['WEBGL_debug_renderer_info'], getContextAttributes: () => ({}), getShaderPrecisionFormat: () => ({ precision: 23, rangeMin: 127, rangeMax: 127 }) };
      return { canvas: this, fillRect() {}, clearRect() {}, getImageData: (x, y, w = 1, h = 1) => ({ data: new Uint8ClampedArray(w * h * 4) }), putImageData() {}, createImageData: (w = 1, h = 1) => ({ data: new Uint8ClampedArray(w * h * 4) }), setTransform() {}, transform() {}, drawImage() {}, save() {}, restore() {}, beginPath() {}, moveTo() {}, lineTo() {}, bezierCurveTo() {}, quadraticCurveTo() {}, closePath() {}, clip() {}, stroke() {}, fill() {}, arc() {}, rect() {}, ellipse() {}, translate() {}, scale() {}, rotate() {}, fillText() {}, strokeText() {}, measureText: (t) => ({ width: ('' + t).length * 8 }), createLinearGradient: () => ({ addColorStop() {} }), createRadialGradient: () => ({ addColorStop() {} }), createPattern: () => ({}), isPointInPath: () => false, font: '10px sans-serif', textBaseline: 'alphabetic', textAlign: 'start', fillStyle: '#000', strokeStyle: '#000', globalAlpha: 1, lineWidth: 1, shadowBlur: 0, shadowColor: '' };
    };
    proto.toDataURL = () => 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';
    proto.toBlob = (cb) => cb && cb(null);
    window.Worker = class { constructor() {} postMessage() {} terminate() {} addEventListener() {} removeEventListener() {} onmessage = null; onerror = null; };
    window.OffscreenCanvas = window.OffscreenCanvas || class { constructor(w, h) { this.width = w; this.height = h; } getContext() { return proto.getContext.call(this); } };

    // fetch/XHR 直连
  },
});

const window = dom.window;

function waitFor(cond, t = 15000) {
  return new Promise((res, rej) => {
    const s = Date.now();
    const i = setInterval(() => {
      let ok = false;
      try { ok = cond(); } catch (_) {}
      if (ok) { clearInterval(i); res(); }
      else if (Date.now() - s > t) { clearInterval(i); rej(new Error('timeout wait')); }
    }, 80);
  });
}

(async () => {
  console.log('appkey=', APPKEY, 'scene=', SCENE, 'region=', REGION);
  // 等 AWSC 加载
  await waitFor(() => typeof window.AWSC === 'object' && typeof window.AWSC.use === 'function', 20000);
  console.log('AWSC loaded');

  window.AWSC.use('nvc', (state, module) => {
    console.log('nvc state=', state);
    if (state !== 'loaded') {
      console.error('nvc 模块未加载成功');
      process.exit(2);
    }
    try {
      const nvc = module.init({
        appkey: APPKEY,
        scene: SCENE,
        success: function (data) { console.log('[success]', data); },
        fail: function (code) { console.log('[fail]', code); },
        error: function (code) { console.log('[error]', code); },
      });
      console.log('nvc init ok, typeof nvc=', typeof nvc);
      console.log('nvc methods:', Object.getOwnPropertyNames(Object.getPrototypeOf(nvc)).concat(Object.keys(nvc)));
      window.nvc = nvc;

      // 主动获取人机信息串
      if (typeof nvc.getNVCValAsync === 'function') {
        console.log('调用 getNVCValAsync...');
        nvc.getNVCValAsync((nvcVal) => {
          console.log('getNVCValAsync 返回:');
          console.log('  类型:', typeof nvcVal);
          console.log('  值:', String(nvcVal).slice(0, 300));
          console.log('  长度:', String(nvcVal).length);
          // 尝试 base64 解码
          try {
            const b = Buffer.from(String(nvcVal), 'base64');
            const j = JSON.parse(b.toString('utf-8'));
            console.log('  解码:', JSON.stringify(j));
            console.log('  字段:', Object.keys(j));
            console.log('  有 securityToken:', 'securityToken' in j);
          } catch (e) {
            console.log('  base64解码失败:', e.message);
          }
          process.exit(0);
        });
      } else {
        console.log('无 getNVCValAsync 方法，方法列表:', Object.keys(nvc));
        // 试 getNVCVal
        if (typeof nvc.getNVCVal === 'function') {
          const v = nvc.getNVCVal();
          console.log('getNVCVal:', String(v).slice(0, 300));
        }
        process.exit(3);
      }
    } catch (e) {
      console.error('init 异常:', e);
      process.exit(4);
    }
  });
})();
