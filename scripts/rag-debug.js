const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ headless: true });
  const p = await b.newPage();
  const logs = [];
  p.on('console', msg => { if(msg.text().includes('RAG')||msg.text().includes('知识库')) logs.push(msg.text()); });
  p.on('pageerror', e => logs.push('ERR: '+e.message));
  await p.goto('http://llm-platform-frontend/login', { timeout: 15000, waitUntil: 'networkidle' });
  const ins = await p.$$('input');
  await ins[0].fill('admin'); await ins[1].fill('admin');
  await p.click('button[type=submit]');
  try { await p.waitForURL('**/dashboard', { timeout: 8000 }); } catch {}

  // First upload a test doc to RAG
  await p.goto('http://llm-platform-frontend/rag', { timeout: 10000, waitUntil: 'networkidle' });
  await p.waitForTimeout(1000);
  // Switch to upload tab
  const tabs = await p.$$('.ant-tabs-tab');
  for (const tab of tabs) { const t = await tab.textContent(); if (t && t.includes('上传')) { await tab.click(); break; } }
  await p.waitForTimeout(500);
  // Upload a test file with Milvus content
  const input = await p.$('input[type=file]');
  if (input) {
    // Can't actually upload in headless - need to manually add to localStorage
    await p.evaluate(() => {
      localStorage.setItem('llm_platform_rag_documents', JSON.stringify([{
        document_id: 'test_1', filename: 'Milvus技术文档.pdf', status: 'indexed',
        chunks_count: 3, file_type: 'PDF', file_size: 5000,
        created_at: new Date().toISOString(),
        chunks: [
          'Milvus是一个开源的向量数据库，专门为AI和机器学习应用设计。它支持十亿级向量搜索，提供HNSW、IVF等多种索引算法。Milvus采用存储计算分离架构，支持水平扩展。',
          'Milvus的核心功能包括：向量相似度搜索、混合搜索（向量+标量过滤）、数据分片、多租户隔离。它提供Python、Java、Go等多种语言SDK。',
          'Milvus与LlamaIndex、LangChain等AI框架深度集成，支持RAG场景。单节点可处理百万级向量，集群模式可扩展到十亿级。',
        ]
      }]));
    });
    console.log('STORED test doc to localStorage');
  }

  // Go to chat and test
  await p.goto('http://llm-platform-frontend/chat', { timeout: 10000, waitUntil: 'networkidle' });
  await p.waitForTimeout(500);
  const ta = await p.$('textarea');
  await ta.fill('Milvus是什么');
  await p.waitForTimeout(300);
  for (const btn of await p.$$('button')) { const t = await btn.textContent(); if (t && t.includes('发送')) { await btn.click(); break; } }
  await p.waitForTimeout(10000);
  const body = await p.textContent('body');
  console.log('CHAT BODY:', body.substring(0, 600));
  console.log('---RAG LOGS---');
  logs.forEach(l => console.log(l));
  await b.close();
})();
