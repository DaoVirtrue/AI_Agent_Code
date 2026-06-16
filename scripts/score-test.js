const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ headless: true });
  const p = await b.newPage();
  await p.goto('http://llm-platform-frontend/login', { timeout: 15000, waitUntil: 'networkidle' });
  const ins = await p.$$('input');
  await ins[0].fill('admin'); await ins[1].fill('admin');
  await p.click('button[type=submit]');
  try { await p.waitForURL('**/dashboard', { timeout: 8000 }); } catch {}
  await p.evaluate(() => {
    localStorage.setItem('llm_platform_rag_documents', JSON.stringify([{
      document_id: 't1', filename: '游戏介绍.md', status: 'indexed', chunks_count: 3, file_type: 'MD', file_size: 500,
      created_at: new Date().toISOString(),
      chunks: [
        '万界神国是一款多人在线角色扮演游戏，由星辰工作室开发。',
        '游戏采用虚幻引擎5打造，拥有宏大的开放世界和创新的战斗系统。',
        '这款游戏的核心玩法包括探索、战斗、养成和社交四大系统。'
      ]
    }]));
  });
  await p.goto('http://llm-platform-frontend/chat', { timeout: 10000, waitUntil: 'networkidle' });
  await p.waitForTimeout(500);
  const ta = await p.$$('textarea');
  await ta[0].fill('万界神国是什么游戏');
  await p.waitForTimeout(300);
  const btns = await p.$$('button');
  for (const btn of btns) { const t = await btn.textContent(); if (t && t.includes('发送')) { await btn.click(); break; } }
  await p.waitForTimeout(8000);
  const tabs = await p.$$('.ant-tabs-tab');
  for (const tab of tabs) { const t = await tab.textContent(); if (t && t.includes('引用')) { await tab.click(); await p.waitForTimeout(500); break; } }
  const scores = await p.evaluate(() => {
    return Array.from(document.querySelectorAll('.ant-tag')).filter(t => t.textContent.includes('%')).map(t => t.textContent.trim());
  });
  console.log('SCORES:', JSON.stringify(scores));
  await b.close();
})();
