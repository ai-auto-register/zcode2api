'use strict';

// 常驻 HTTP 服务，供 Python 端调用求解阿里云无痕验证。
//
// 求解时 jsdom 内阿里云 SDK 发起的 HTTP 请求（fetch/XHR）被桩拦截，
// 转发给 Python /internal/rnet-proxy 回调，由 rnet (Chrome131) 实际发出。
// 业务请求也用同一个 rnet Client，TLS/UA/出口 IP 完全一致。
//
// 路由：
//   POST /solve     {scene, region, prefix, reverse_url}  -> {ok, verify_param} | {ok:false, error}
//   GET  /healthz                                        -> {ok:true}

require('global-agent/bootstrap');

const http = require('http');
const { createDom, solveCaptcha } = require('./solver_core');

const PORT = parseInt(process.env.SOLVER_PORT || '0', 10);
const HOST = process.env.SOLVER_HOST || '127.0.0.1';
const USER_AGENT = process.env.ZCODE_UA || 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36';
const CALLBACK_URL = process.env.RNET_CALLBACK_URL || '';
const CALLBACK_TOKEN = process.env.RNET_CALLBACK_TOKEN || '';

// ── 全局长驻 jsdom 实例 ────────────────────────────────────────────────────
let _dom = null;

function getDom() {
  if (_dom) return _dom;
  _dom = createDom({
    userAgent: USER_AGENT,
    callbackUrl: CALLBACK_URL,
    callbackToken: CALLBACK_TOKEN,
  });
  return _dom;
}

function sendJson(res, status, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(status, { 'content-type': 'application/json; charset=utf-8', 'content-length': Buffer.byteLength(body) });
  res.end(body);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on('data', (c) => chunks.push(c));
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', reject);
  });
}

// ── /solve ──────────────────────────────────────────────────────────────────
async function handleSolve(req, res) {
  const raw = (await readBody(req)).toString('utf-8');
  let payload = {};
  try { payload = JSON.parse(raw || '{}'); } catch (_) { return sendJson(res, 400, { ok: false, error: 'invalid json' }); }

  const scene = payload.scene || '11xygtvd';
  const region = payload.region || 'sgp';
  const prefix = payload.prefix || 'no8xfe';
  const timeoutMs = Math.min(Math.max(parseInt(payload.timeout_ms, 10) || 25000, 5000), 60000);

  try {
    const dom = getDom();
    const param = await solveCaptcha(dom, scene, region, prefix, timeoutMs);
    return sendJson(res, 200, { ok: true, verify_param: param });
  } catch (e) {
    return sendJson(res, 500, { ok: false, error: String(e && e.message || e) });
  }
}

const server = http.createServer(async (req, res) => {
  try {
    if (req.method === 'GET' && req.url === '/healthz') return sendJson(res, 200, { ok: true });
  } catch (_) {}
  try {
    if (req.method === 'POST' && req.url === '/solve') return await handleSolve(req, res);
  } catch (e) {
    return sendJson(res, 500, { ok: false, error: String(e && e.message || e) });
  }
  return sendJson(res, 404, { ok: false, error: 'not found' });
});

if (!PORT) {
  console.error('SOLVER_PORT 未设置');
  process.exit(1);
}

// 启动时预建 jsdom（resources:usable 会异步加载阿里云 SDK，提前预热）
getDom();

server.listen(PORT, HOST, () => {
  const hasCallback = CALLBACK_URL ? 'rnet-callback=' + CALLBACK_URL : 'no-callback';
  console.log(`solver-server listening on http://${HOST}:${PORT} (ua=${USER_AGENT}, ${hasCallback})`);
});

// keep-alive
setInterval(() => {}, 30000);

// jsdom 异步异常守护
const _seenErrors = new Set();
process.on('uncaughtException', (err) => {
  const key = (err && err.stack || String(err)).slice(0, 200);
  if (!_seenErrors.has(key)) {
    _seenErrors.add(key);
    if (process.env.SOLVER_DEBUG) console.error('[uncaught]', key);
  }
});
process.on('unhandledRejection', (reason) => {
  const k2 = String(reason && reason.stack || reason).slice(0, 200);
  if (!_seenErrors.has(k2)) {
    _seenErrors.add(k2);
    if (process.env.SOLVER_DEBUG) console.error('[unhandledRejection]', k2);
  }
});

process.stdin.on('close', () => process.exit(0));
process.on('SIGTERM', () => process.exit(0));
process.on('SIGINT', () => process.exit(0));
