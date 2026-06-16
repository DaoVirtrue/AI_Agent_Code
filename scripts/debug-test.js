const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ headless: true });
  const p = await b.newPage();
  const allLogs = [];
  p.on('console', msg => allLogs.push(`[${msg.type()}] ${msg.text()}`));
  p.on('pageerror', err => allLogs.push(`[ERR] ${err.message}`));

  // Login
  await p.goto('http://llm-platform-frontend/login', { timeout: 15000, waitUntil: 'networkidle' });
  const inputs = await p.$$('input');
  await inputs[0].fill('admin'); await inputs[1].fill('admin');
  await p.click('button[type="submit"]');
  try { await p.waitForURL('**/dashboard', { timeout: 8000 }); } catch {}

  // Test each page
  const pages = [
    { url: '/rag', name: 'RAG', action: async () => {
      const ta = await p.$('textarea');
      if (ta) { await ta.fill('什么是RAG'); await p.waitForTimeout(500);
        const btns = await p.$$('button');
        for (const b of btns) { const t = await b.textContent(); if (t.includes('搜索')) { await b.click(); break; } }
        await p.waitForTimeout(2000); }
    }},
    { url: '/agent', name: 'Agent', action: async () => {
      const ta = await p.$('textarea');
      if (ta) { await ta.fill('分析系统性能'); await p.waitForTimeout(500);
        const btns = await p.$$('button');
        for (const b of btns) { const t = await b.textContent(); if (t.includes('执行')||t.includes('运行')) { await b.click(); break; } }
        await p.waitForTimeout(3000); }
    }},
    { url: '/prompts', name: 'Prompts', action: async () => {
      await p.waitForTimeout(1000);
      const btns = await p.$$('button');
      for (const b of btns) { const t = await b.textContent(); if (t.includes('创建')||t.includes('新建')) { await b.click(); break; } }
      await p.waitForTimeout(1000);
    }},
    { url: '/gateway', name: 'Gateway', action: async () => { await p.waitForTimeout(1000); }},
  ];

  for (const page of pages) {
    await p.goto('http://llm-platform-frontend' + page.url, { timeout: 10000, waitUntil: 'networkidle' });
    await p.waitForTimeout(1500);
    await page.action();
    const body = await p.textContent('body');
    process.stdout.write('\n=== ' + page.name + ' (' + page.url + ') ===\n');
    process.stdout.write('BODY(500): ' + (body||'').substring(0, 500) + '\n');
    process.stdout.write('TEXTAREA: ' + (await p.evaluate(() => document.querySelectorAll('textarea').length)) + '\n');
  }

  process.stdout.write('\n--- LOGS ---\n');
  allLogs.filter(l => l.includes('ERR') || l.includes('error')).forEach(l => process.stdout.write(l + '\n'));
  await b.close();
})();
