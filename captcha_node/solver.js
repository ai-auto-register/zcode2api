'use strict';

// CLI 入口：保持原有参数兼容（scene region prefix reverse_url）。
// CLI 模式不使用 Python rnet 回调（无 callback），走 jsdom 自带 XHR。
// 用法: node solver.js [scene] [region] [prefix] [reverse_url]

require('global-agent/bootstrap');

const { createDom, solveCaptcha } = require('./solver_core');

const SCENE = process.argv[2] || '11xygtvd';
const REGION = process.argv[3] || 'sgp';
const PREFIX = process.argv[4] || 'no8xfe';
const REVERSE_URL = process.argv[5] || '';

(async () => {
  const dom = createDom({ reverseUrl: REVERSE_URL });
  try {
    const param = await solveCaptcha(dom, SCENE, REGION, PREFIX, 25000);
    console.log('VERIFY_PARAM=' + param);
    process.exit(0);
  } catch (e) {
    if (process.env.SOLVER_DEBUG) console.error(e);
    process.exit(4);
  }
})();
