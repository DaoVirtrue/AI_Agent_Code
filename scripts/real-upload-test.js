const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ headless: true });
  const p = await b.newPage();
  const logs = [];
  p.on('console', msg => logs.push(msg.text()));

  await p.goto('http://llm-platform-frontend/login', { timeout: 15000, waitUntil: 'networkidle' });
  const ins = await p.$$('input');
  await ins[0].fill('admin'); await ins[1].fill('admin');
  await p.click('button[type=submit]');
  try { await p.waitForURL('**/dashboard', { timeout: 8000 }); } catch {}

  // Go to RAG, upload tab
  await p.goto('http://llm-platform-frontend/rag', { timeout: 10000, waitUntil: 'networkidle' });
  await p.waitForTimeout(1000);
  const tabs = await p.$$('.ant-tabs-tab');
  for (const tab of tabs) { const t = await tab.textContent(); if (t && t.includes('上传')) { await tab.click(); break; } }
  await p.waitForTimeout(500);

  // Create a test file and upload via file chooser
  const [fileChooser] = await Promise.all([
    p.waitForEvent('filechooser'),
    p.click('.ant-upload-drag-container, .ant-upload-btn')
  ]);

  // Create a temp file with test content
  await fileChooser.setFiles({
    name: 'Milvus介绍.md',
    mimeType: 'text/markdown',
    buffer: Buffer.from('Milvus是一个开源的向量数据库，专门为AI和机器学习应用设计。它支持十亿级向量搜索，提供HNSW、IVF等多种索引算法。Milvus采用存储计算分离架构。核心功能包括向量相似度搜索、混合搜索、数据分片、多租户隔离。'),
  });

  await p.waitForTimeout(2000);
  const body0 = await p.textContent('body');
  console.log('UPLOAD_RESULT:', body0.includes('Milvus介绍.md') ? 'FILE_UPLOADED' : 'NOT_FOUND');

  // Check localStorage
  const docs = await p.evaluate(() => {
    try { return JSON.parse(localStorage.getItem('llm_platform_rag_documents') || '[]'); } catch { return []; }
  });
  console.log('DOCS_AFTER_UPLOAD:', docs.length);
  if (docs.length > 0) console.log('  First doc:', docs[0].filename, 'chunks:', (docs[0].chunks||[]).length, 'firstChunkLen:', (docs[0].chunks||[])[0]?.length || 0);

  // Now go to Chat
  await p.goto('http://llm-platform-frontend/chat', { timeout: 10000, waitUntil: 'networkidle' });
  await p.waitForTimeout(500);
  const ta = await p.$('textarea');
  await ta.fill('Milvus是什么');
  await p.waitForTimeout(300);
  for (const btn of await p.$$('button')) { const t = await btn.textContent(); if (t && t.includes('发送')) { await btn.click(); break; } }
  await p.waitForTimeout(8000);
  const body = await p.textContent('body');
  console.log('CHAT_RAG:', body.includes('十亿级') ? 'USING_DOC' : 'NO_RAG');

  const ragLogs = logs.filter(l => l.includes('RAG'));
  console.log('RAG_LOGS:', ragLogs.join(' | '));

  await b.close();
})();
