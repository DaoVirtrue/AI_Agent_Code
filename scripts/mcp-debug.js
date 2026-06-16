const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ headless: true });
  const p = await b.newPage();
  const errs = [];
  p.on('pageerror', e => errs.push(e.message));
  p.on('console', m => { if(m.type()==='error') errs.push(m.text()); });
  await p.goto('http://llm-platform-frontend/login', { timeout: 15000, waitUntil: 'networkidle' });
  const ins = await p.$$('input');
  await ins[0].fill('admin'); await ins[1].fill('admin');
  await p.click('button[type=submit]');
  try { await p.waitForURL('**/dashboard', { timeout: 8000 }); } catch {}
  await p.goto('http://llm-platform-frontend/mcp', { timeout: 10000, waitUntil: 'networkidle' });
  await p.waitForTimeout(3000);
  const html = await p.evaluate(() => {
    const table = document.querySelector('.ant-table');
    return table ? table.textContent.substring(0, 500) : 'NO TABLE';
  });
  console.log('TABLE:', html);
  console.log('ERRORS:', errs.join(' | ') || 'none');
  await b.close();
})();
