const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ headless: true });
  const p = await b.newPage();
  await p.goto('http://llm-platform-frontend/login', { timeout: 15000, waitUntil: 'networkidle' });
  const ins = await p.$$('input');
  await ins[0].fill('admin'); await ins[1].fill('admin');
  await p.click('button[type="submit"]');
  try { await p.waitForURL('**/dashboard', { timeout: 8000 }); } catch {}

  await p.goto('http://llm-platform-frontend/gateway', { timeout: 10000, waitUntil: 'networkidle' });
  await p.waitForTimeout(1500);
  let body = await p.textContent('body');
  console.log('GATEWAY:', body.includes('健康') ? 'OK' : 'NO_HEALTH', body.includes('不可用') ? 'HAS_不可用' : '');

  await p.goto('http://llm-platform-frontend/mcp', { timeout: 10000, waitUntil: 'networkidle' });
  await p.waitForTimeout(1500);
  body = await p.textContent('body');
  console.log('MCP 5 servers:', body.includes('文件系统'), body.includes('网络搜索'), body.includes('数据库'), body.includes('GitHub'), body.includes('REST API'));
  await b.close();
})();
