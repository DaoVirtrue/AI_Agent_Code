const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ headless: true });
  const p = await b.newPage();
  const logs = [];
  p.on('console', msg => logs.push(msg.text()));
  p.on('pageerror', e => logs.push('ERR: '+e.message));

  await p.goto('http://llm-platform-frontend/login', { timeout: 15000, waitUntil: 'networkidle' });
  const ins = await p.$$('input');
  await ins[0].fill('admin'); await ins[1].fill('admin');
  await p.click('button[type=submit]');
  try { await p.waitForURL('**/dashboard', { timeout: 8000 }); } catch {}

  // Check localStorage for existing docs
  const existingDocs = await p.evaluate(() => {
    try { return JSON.parse(localStorage.getItem('llm_platform_rag_documents') || '[]'); } catch { return []; }
  });
  console.log('Existing docs:', existingDocs.length);
  existingDocs.forEach(d => console.log('  Doc:', d.filename, 'chunks:', (d.chunks||[]).length));

  // If no docs, upload a test one
  if (existingDocs.length === 0) {
    // Go to RAG, upload a simple file
    // We can't actually upload files in headless Playwright easily
    // So inject a doc directly
    await p.evaluate(() => {
      localStorage.setItem('llm_platform_rag_documents', JSON.stringify([{
        document_id: 'test', filename: '测试文档.md', status: 'indexed',
        chunks_count: 2, file_type: 'MD', file_size: 500,
        created_at: new Date().toISOString(),
        chunks: [
          'Milvus是一个开源的向量数据库，支持十亿级向量搜索和混合检索。',
          'LangGraph是用于构建有状态多Agent应用的框架，支持循环和条件路由。'
        ]
      }]));
    });
    console.log('Injected test doc');
  }

  // Now go to chat
  await p.goto('http://llm-platform-frontend/chat', { timeout: 10000, waitUntil: 'networkidle' });
  await p.waitForTimeout(500);
  const ta = await p.$('textarea');
  await ta.fill('Milvus是什么');
  await p.waitForTimeout(300);
  for (const btn of await p.$$('button')) { const t = await btn.textContent(); if (t && t.includes('发送')) { await btn.click(); break; } }
  await p.waitForTimeout(10000);
  const body = await p.textContent('body');
  console.log('HAS_RAG:', body.includes('十亿级') || body.includes('向量数据库'));
  console.log('HAS_GENERIC:', body.includes('开源'));

  // Check RAG logs
  const ragLogs = logs.filter(l => l.includes('RAG'));
  console.log('RAG_LOGS:', ragLogs.join(' | '));

  await b.close();
})();
