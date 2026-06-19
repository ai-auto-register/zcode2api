'use strict';

// 独立测试：直接运行，不走 server.js，看 SDK 到底发了什么请求。
// 用法: set SOLVER_DEBUG=1 && node test_trace.js

require('global-agent/bootstrap');

const { JSDOM, VirtualConsole } = require('jsdom');

const SCENE = '11xygtvd';
const REGION = 'sgp';
const PREFIX = 'no8xfe';
const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36';

const html = `<!DOCTYPE html><html><head></head><body>
<div id="cap"></div><button id="btn"></button>
<script src="https://o.alicdn.com/captcha-frontend/aliyunCaptcha/AliyunCaptcha.js"></script>
</body></html>`;

const vc = new VirtualConsole();
vc.on('jsdomError', (e) => console.error('[jsdomError]', e.message));
vc.on('error', (...a) => console.error('[console.error]', ...a));
vc.on('warn', (...a) => console.error('[console.warn]', ...a));
vc.on('log', (...a) => console.log('[console.log]', ...a));
vc.on('info', (...a) => console.log('[console.info]', ...a));

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

    // ── 补齐浏览器环境，绕过 cloudauth-device 设备指纹检测 ──────────────
    // window.chrome
    window.chrome = {
      runtime: {},
      loadTimes: () => ({}),
      csi: () => ({}),
      app: { isInstalled: false },
      webstore: {},
    };
    // navigator.plugins / mimeTypes
    try {
      const fakePlugin = Object.create(window.Plugin.prototype || Object.prototype);
      Object.defineProperties(fakePlugin, {
        name: { value: 'Chrome PDF Plugin' },
        filename: { value: 'internal-pdf-viewer' },
        description: { value: 'Portable Document Format' },
        length: { value: 1 },
      });
      const fakePlugin2 = Object.create(window.Plugin.prototype || Object.prototype);
      Object.defineProperties(fakePlugin2, {
        name: { value: 'Chrome PDF Viewer' },
        filename: { value: 'internal-pdf-viewer' },
        description: { value: '' },
        length: { value: 1 },
      });
      const plugins = [fakePlugin, fakePlugin2];
      Object.defineProperty(window.navigator, 'plugins', { get: () => plugins, configurable: true });
      Object.defineProperty(window.navigator, 'mimeTypes', { get: () => [], configurable: true });
    } catch (_) {}
    // navigator.languages
    try { Object.defineProperty(window.navigator, 'languages', { get: () => ['en-US', 'en'], configurable: true }); } catch (_) {}
    // navigator.platform
    try { Object.defineProperty(window.navigator, 'platform', { get: () => 'MacIntel', configurable: true }); } catch (_) {}
    // navigator.webdriver
    try { Object.defineProperty(window.navigator, 'webdriver', { get: () => false, configurable: true }); } catch (_) {}
    // navigator.permissions
    if (!window.navigator.permissions) {
      window.navigator.permissions = { query: () => Promise.resolve({ state: 'prompt', onchange: null }) };
    }
    // window.Notification
    if (!window.Notification) { window.Notification = class { static permission = 'default'; static requestPermission = () => Promise.resolve('default'); }; }
    // screen
    try {
      Object.defineProperties(window.screen, {
        width: { get: () => 1920, configurable: true },
        height: { get: () => 1080, configurable: true },
        availWidth: { get: () => 1920, configurable: true },
        availHeight: { get: () => 1050, configurable: true },
        colorDepth: { get: () => 24, configurable: true },
        pixelDepth: { get: () => 24, configurable: true },
      });
    } catch (_) {}
    // devicePixelRatio
    try { Object.defineProperty(window, 'devicePixelRatio', { get: () => 1, configurable: true }); } catch (_) {}
    // localStorage / sessionStorage（jsdom 通常有，但保险）
    if (!window.localStorage) { window.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {}, clear: () => {}, key: () => null, length: 0 }; }
    if (!window.sessionStorage) { window.sessionStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {}, clear: () => {}, key: () => null, length: 0 }; }
    // Performance API
    if (!window.performance) { window.performance = { now: () => Date.now(), timing: {}, getEntries: () => [], getEntriesByType: () => [], mark: () => {}, measure: () => {} }; }
    // Crypto subtle
    if (window.crypto && !window.crypto.subtle) { window.crypto.subtle = { digest: () => Promise.resolve(new ArrayBuffer(32)) }; }


    const REVERSE_URL = '';  // 直连阿里云
    function applyReverse(url) {
      return url;
    }

    // 拦截所有网络请求方式 + reverse_url 前缀
    const _origFetch = window.fetch;
    window.fetch = async function (input, init) {
      const url = typeof input === 'string' ? input : (input && input.url) || '';
      const method = (init && init.method) || 'GET';
      const finalUrl = applyReverse(url);
      console.error(`[FETCH] ${method} ${url.slice(0, 90)} -> ${finalUrl.slice(0, 90)}`);
      const newInput = typeof input === 'string' ? finalUrl : (input.url = finalUrl, input);
      const result = await _origFetch.call(this, newInput, init);
      console.error(`[FETCH->] ${url.slice(0, 60)} status=${result.status}`);
      return result;
    };

    const _OrigXHR = window.XMLHttpRequest;
    window.XMLHttpRequest = class extends _OrigXHR {
      open(method, url, ...rest) {
        this._dbgMethod = method;
        this._dbgUrl = url;
        const finalUrl = applyReverse(url);
        console.error(`[XHR open] ${method} ${String(url).slice(0, 90)}`);
        return super.open(method, finalUrl, ...rest);
      }
      send(body) {
        console.error(`[XHR send] ${this._dbgMethod || '?'} ${String(this._dbgUrl || '').slice(0, 80)}`);
        if (body) {
          const bodyStr = typeof body === 'string' ? body : (body && body.toString ? body.toString() : '');
          console.error(`[XHR body] ${bodyStr.slice(0, 300)}`);
        }
        const origOnload = this.onload;
        this.addEventListener('load', () => {
          console.error(`[XHR resp] ${this._dbgUrl.slice(0, 60)} status=${this.status} body=${this.responseText.slice(0, 300)}`);
        });
        return super.send(body);
      }
    };

    // 拦截 script 标签创建（JSONP）
    const _origCreateElement = window.document.createElement.bind(window.document);
    window.document.createElement = function (tag) {
      const el = _origCreateElement(tag);
      if (tag.toLowerCase() === 'script') {
        const _origSrc = Object.getOwnPropertyDescriptor(window.HTMLScriptElement.prototype, 'src');
        Object.defineProperty(el, 'src', {
          set(v) {
            console.error(`[SCRIPT src] ${String(v).slice(0, 120)}`);
            _origSrc.set.call(this, v);
          },
          get() { return _origSrc.get.call(this); },
        });
      }
      return el;
    };
  },
});

const window = dom.window;

function waitFor(cond, t = 20000) {
  return new Promise((res, rej) => {
    const s = Date.now();
    const i = setInterval(() => {
      let ok = false;
      try { ok = cond(); } catch (_) {}
      if (ok) { clearInterval(i); res(); }
      else if (Date.now() - s > t) { clearInterval(i); rej(new Error('timeout')); }
    }, 80);
  });
}

(async () => {
  console.log('等待 initAliyunCaptcha...');
  await waitFor(() => typeof window.initAliyunCaptcha === 'function', 20000);
  console.log('initAliyunCaptcha 可用');

  window.AliyunCaptchaConfig = { region: REGION, prefix: PREFIX };

  let instanceResolve;
  const instancePromise = new Promise((res) => { instanceResolve = res; });

  window.initAliyunCaptcha({
    SceneId: SCENE,
    mode: 'popup',
    captchaLogoImg: undefined,
    showErrorTip: false,
    element: '#cap',
    button: '#btn',
    getInstance: (inst) => {
      console.log('[getInstance] instance ready');
      console.log('[getInstance] methods:', Object.getOwnPropertyNames(Object.getPrototypeOf(inst)).concat(Object.keys(inst)));
      instanceResolve(inst);
    },
    success: (param) => {
      console.log('\n[success] param:');
      console.log('  长度:', param.length);
      console.log('  值:', param.slice(0, 200));
      try {
        const j = JSON.parse(Buffer.from(param, 'base64').toString('utf-8'));
        console.log('  解码:', JSON.stringify(j));
        console.log('  字段:', Object.keys(j));
        console.log('  有 securityToken:', 'securityToken' in j);
      } catch (e) {
        console.log('  base64解码失败:', e.message);
      }
      process.exit(0);
    },
    fail: (err) => {
      console.log('[fail]', JSON.stringify(err));
    },
    onError: (err) => {
      console.log('[onError]', err);
    },
  });

  const inst = await instancePromise;
  console.log('\n等待 2 秒后调用 startTracelessVerification...');
  await new Promise(r => setTimeout(r, 2000));

  if (typeof inst.startTracelessVerification === 'function') {
    console.log('调用 startTracelessVerification()');
    inst.startTracelessVerification();
  } else if (typeof inst.show === 'function') {
    console.log('调用 show()');
    inst.show();
  } else {
    console.log('无 startTracelessVerification/show，触发按钮 click');
    window.document.getElementById('btn').click();
  }

  // 等待 30 秒
  setTimeout(() => {
    console.error('超时退出');
    process.exit(1);
  }, 30000);
})();
