'use strict';

// 验证码求解核心 jsdom 环境，供 solver.js（CLI）与 server.js（HTTP 服务）共用。
//
// 关键设计：
//  jsdom 内阿里云 SDK 发起的所有 HTTP 请求（fetch / XHR）都被桩拦截，
//  转发给 Python /internal/rnet-proxy 回调，由 Python rnet (Chrome131) 实际发出。
//  这样求解阶段与业务请求阶段的 TLS/UA/出口 IP 完全一致。

const { JSDOM, VirtualConsole } = require('jsdom');
const http = require('http');
const https = require('https');

const DEFAULT_UA = process.env.ZCODE_UA || 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36';

/**
 * 调用 Python /internal/rnet-proxy 回调，用 rnet (Chrome131) 发出实际请求。
 * @returns {Promise<{status:number, headers:object, body:Buffer}>}
 */
function proxyViaPython(callbackUrl, callbackToken, method, url, headers, body) {
  const reqHeaders = { 'content-type': 'application/json', 'x-rnet-token': callbackToken };
  // body 转 base64
  let bodyB64 = '';
  if (body) {
    const buf = Buffer.isBuffer(body) ? body : Buffer.from(typeof body === 'string' ? body : String(body));
    bodyB64 = buf.toString('base64');
  }
  const payload = JSON.stringify({ method, url, headers: headers || {}, body: bodyB64 });

  return new Promise((resolve, reject) => {
    const u = new URL(callbackUrl);
    const lib = u.protocol === 'https:' ? https : http;
    const req = lib.request({
      hostname: u.hostname,
      port: u.port,
      path: u.pathname + u.search,
      method: 'POST',
      headers: { ...reqHeaders, 'content-length': Buffer.byteLength(payload) },
    }, (res) => {
      const chunks = [];
      res.on('data', (c) => chunks.push(c));
      res.on('end', () => {
        const raw = Buffer.concat(chunks).toString('utf-8');
        try {
          const obj = JSON.parse(raw);
          if (obj.error) {
            reject(new Error('rnet-proxy error: ' + obj.error));
            return;
          }
          const status = obj.status || 0;
          const respHeaders = obj.headers || {};
          const data = obj.body ? Buffer.from(obj.body, 'base64') : Buffer.alloc(0);
          resolve({ status, headers: respHeaders, body: data });
        } catch (e) {
          reject(new Error('rnet-proxy parse: ' + e.message + ' raw=' + raw.slice(0, 200)));
        }
      });
    });
    req.on('error', (e) => reject(new Error('rnet-proxy connect: ' + e.message)));
    req.setTimeout(30000, () => { req.destroy(new Error('rnet-proxy timeout')); });
    req.write(payload);
    req.end();
  });
}

/**
 * 构造一个 jsdom 实例。
 * @param {object} opts
 * @param {string} opts.userAgent
 * @param {string} opts.callbackUrl    Python /internal/rnet-proxy 回调地址
 * @param {string} opts.callbackToken   共享密钥
 */
function createDom(opts = {}) {
  const userAgent = opts.userAgent || DEFAULT_UA;
  const callbackUrl = opts.callbackUrl || '';
  const callbackToken = opts.callbackToken || '';
  const reverseUrl = opts.reverseUrl || '';
  const useProxy = !!(callbackUrl && callbackToken);

  const vc = new VirtualConsole();
  const html = `<!DOCTYPE html><html><head></head><body>
<div id="cap"></div><button id="btn"></button>
<script src="https://o.alicdn.com/captcha-frontend/aliyunCaptcha/AliyunCaptcha.js"></script>
</body></html>`;

  const dom = new JSDOM(html, {
    url: 'https://zcode.z.ai/',
    runScripts: 'dangerously',
    resources: 'usable',
    pretendToBeVisual: true,
    virtualConsole: vc,
    beforeParse(window) {
      // UA：CLI 模式用 jsdom 默认 UA；callback 模式用 Chrome131
      if (useProxy) {
        try {
          Object.defineProperty(window.navigator, 'userAgent', { get: () => userAgent, configurable: true });
        } catch (_) {}
      }

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

      // ── 核心：把 fetch / XHR 桩成调用 Python rnet 回调 ──────────────────
      if (useProxy) {
        // fetch 桩：返回 Promise<Response-like>
        window.fetch = async function (input, init) {
          const url = typeof input === 'string' ? input : (input && input.url) || '';
          const method = (init && init.method) || 'GET';
          const headers = {};
          if (init && init.headers) {
            if (init.headers instanceof Headers) {
              init.headers.forEach((v, k) => { headers[k] = v; });
            } else if (Array.isArray(init.headers)) {
              for (const [k, v] of init.headers) { headers[k] = v; }
            } else {
              Object.assign(headers, init.headers);
            }
          }
          const body = init && init.body ? init.body : null;
          const r = await proxyViaPython(callbackUrl, callbackToken, method, url, headers, body);
          if (process.env.SOLVER_DEBUG) {
            const preview = r.body.toString('utf-8').slice(0, 200);
            console.error(`[fetch] ${method} ${url.slice(0, 90)} -> ${r.status} | ${preview}`);
          }
          const respHeaders = new Map(Object.entries(r.headers));
          return {
            ok: r.status >= 200 && r.status < 300,
            status: r.status,
            statusText: '',
            headers: {
              get: (k) => respHeaders.get(k.toLowerCase()) || null,
              forEach: (cb) => respHeaders.forEach((v, k) => cb(v, k)),
            },
            text: async () => r.body.toString('utf-8'),
            json: async () => JSON.parse(r.body.toString('utf-8')),
            arrayBuffer: async () => r.body.buffer.slice(r.body.byteOffset, r.body.byteOffset + r.body.byteLength),
          };
        };

        // XHR 桩：实现阿里云 SDK 用到的子集
        window.XMLHttpRequest = class {
          constructor() {
            this.readyState = 0;
            this.status = 0;
            this.statusText = '';
            this.responseText = '';
            this.response = '';
            this.responseType = '';
            this.timeout = 0;
            this._method = 'GET';
            this._url = '';
            this._headers = {};
            this.onload = null;
            this.onerror = null;
            this.ontimeout = null;
            this._timeoutTimer = null;
          }
          open(method, url) { this._method = method; this._url = url; this.readyState = 1; }
          setRequestHeader(k, v) { this._headers[k] = v; }
          send(body) {
            this.readyState = 2;
            const doReq = async () => {
              try {
                if (this._timeoutTimer) clearTimeout(this._timeoutTimer);
                if (this.timeout > 0) {
                  this._timeoutTimer = setTimeout(() => {
                    if (this.ontimeout) this.ontimeout();
                  }, this.timeout);
                }
                const r = await proxyViaPython(callbackUrl, callbackToken, this._method, this._url, this._headers, body);
                if (this._timeoutTimer) clearTimeout(this._timeoutTimer);
                if (process.env.SOLVER_DEBUG) {
                  const preview = r.body.toString('utf-8').slice(0, 200);
                  console.error(`[xhr] ${this._method} ${this._url.slice(0, 90)} -> ${r.status} | ${preview}`);
                }
                this.status = r.status;
                this.responseText = r.body.toString('utf-8');
                this.response = this.responseText;
                this.readyState = 4;
                if (this.onload) this.onload();
              } catch (e) {
                if (this._timeoutTimer) clearTimeout(this._timeoutTimer);
                this.readyState = 4;
                this.status = 0;
                if (this.onerror) this.onerror(e);
              }
            };
            doReq();
          }
          abort() { this.readyState = 0; }
          addEventListener() {}
          removeEventListener() {}
        };
      } else if (reverseUrl) {
        // 无 callback 模式（CLI）：保留原来的 REVERSE_URL 前缀拦截
        const _origFetch = window.fetch;
        if (_origFetch) {
          window.fetch = function (url, init) {
            if (typeof url === 'string' && url.indexOf(reverseUrl) !== 0) {
              url = reverseUrl + url;
            }
            return _origFetch.call(this, url, init);
          };
        }
        const _OrigXHR = window.XMLHttpRequest;
        window.XMLHttpRequest = class extends _OrigXHR {
          open(method, url, ...rest) {
            if (typeof url === 'string' && url.indexOf(reverseUrl) !== 0) {
              url = reverseUrl + url;
            }
            return super.open(method, url, ...rest);
          }
        };
      }
    },
  });
  return dom;
}

function waitFor(window, cond, t = 12000) {
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

/**
 * 求解阿里云无痕验证，返回 verifyParam。
 * @param {object} dom    由 createDom 创建的 jsdom 实例
 * @param {string} scene
 * @param {string} region
 * @param {string} prefix
 * @param {number} timeoutMs 整体超时（毫秒）
 * @returns {Promise<string>}
 */
async function solveCaptcha(dom, scene, region, prefix, timeoutMs = 25000) {
  const window = dom.window;
  await waitFor(window, () => typeof window.initAliyunCaptcha === 'function');

  return new Promise((resolve, reject) => {
    let done = false;
    const finish = (fn) => { if (done) return; done = true; fn(); };
    const timer = setTimeout(() => finish(() => reject(new Error('求解超时'))), timeoutMs);
    const safeReject = (e) => { finish(() => process.nextTick(() => reject(e))); };

    let instanceResolve, instanceReject;
    const instancePromise = new Promise((res, rej) => { instanceResolve = res; instanceReject = rej; });

    try {
      window.AliyunCaptchaConfig = { region, prefix };
      window.initAliyunCaptcha({
        SceneId: scene,
        mode: 'popup',
        captchaLogoImg: undefined,
        showErrorTip: false,
        element: '#cap',
        button: '#btn',
        getInstance: (inst) => {
          instanceResolve(inst);
        },
        success: (param) => finish(() => { clearTimeout(timer); resolve(String(param)); }),
        fail: (err) => {
          if (process.env.SOLVER_DEBUG) console.error('[captcha fail]', JSON.stringify(err));
          safeReject(new Error('captcha fail'));
        },
        onError: (err) => {
          if (process.env.SOLVER_DEBUG) console.error('[captcha error]', err);
          safeReject(new Error('captcha error'));
        },
      });
    } catch (e) {
      clearTimeout(timer);
      safeReject(e);
      return;
    }

    (async () => {
      try {
        const inst = await Promise.race([
          instancePromise,
          new Promise((_, rej) => setTimeout(() => rej(new Error('Instance timed out')), 10000)),
        ]);
        if (typeof inst.startTracelessVerification === 'function') {
          inst.startTracelessVerification();
        } else if (typeof inst.show === 'function') {
          inst.show();
        } else {
          window.document.getElementById('btn') && window.document.getElementById('btn').click();
        }
      } catch (e) {
        safeReject(new Error('start: ' + e.message));
      }
    })();
  });
}

module.exports = { createDom, solveCaptcha, waitFor, DEFAULT_UA };
