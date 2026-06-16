const { chromium } = require('playwright');
const BASE = 'http://llm-platform-frontend';

// Test runner
const results = [];
let passed = 0;
let failed = 0;

async function test(name, fn) {
  process.stdout.write(`  [....] ${name}... `);
  try {
    await fn();
    process.stdout.write('PASS\n');
    results.push({ name, status: 'PASS' });
    passed++;
  } catch (e) {
    process.stdout.write(`FAIL: ${e.message}\n`);
    results.push({ name, status: 'FAIL', error: e.message });
    failed++;
  }
}

function section(title) {
  process.stdout.write(`\n${'='.repeat(60)}\n`);
  process.stdout.write(`  ${title}\n`);
  process.stdout.write(`${'='.repeat(60)}\n`);
}

// ---------------------------------------------------------------------------
// Helper: check that a page has Chinese text and minimal unexpected English
// ---------------------------------------------------------------------------
// "AI terms" (English allowed): model names, provider names, technical acronyms
const ALLOWED_ENGLISH = [
  'API', 'Token', 'GPT', 'Prompt', 'RAG', 'Agent', 'MCP', 'Gateway',
  'OpenAI', 'Anthropic', 'DeepSeek', 'Google', 'Meta', 'Mistral',
  'JSON', 'Markdown', 'CSV', 'PDF', 'DOCX', 'TXT',
  'vLLM', 'Provider', 'Key', 'Keys',
  'Claude', 'Sonnet', 'Haiku', 'Opus',
  'RPM', 'Cost', 'Trend', 'SSE', 'Nginx',
  'Redis', 'Max Tokens', 'Completion', 'Streaming',
];

const SUSPICIOUS_ENGLISH = [
  'Search Documents', 'Upload Files', 'Agent Type', 'Task Description',
  'Provider Health', 'Server List', 'Add Server', 'Generate Key',
  'Template List', 'Editor Tab', 'Run Agent', 'System Settings',
  'Audit Log', 'Usage Report', 'Tenant Management',
  'N/A', 'Search', 'Upload', 'Download', 'Settings',
];

function hasChinese(text) {
  // Check if text contains at least some CJK characters
  return /[一-鿿㐀-䶿]/.test(text);
}

function hasSuspiciousEnglish(text) {
  for (const phrase of SUSPICIOUS_ENGLISH) {
    if (text.includes(phrase)) return phrase;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Main test suite
// ---------------------------------------------------------------------------
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  page.on('pageerror', (e) => process.stdout.write(`\n  [PAGE_ERROR] ${e.message}\n`));

  // =========================================================================
  // 1. LOGIN FLOW
  // =========================================================================
  section('1. LOGIN FLOW');

  await test('Login page loads successfully', async () => {
    await page.goto(`${BASE}/login`, { timeout: 15000, waitUntil: 'networkidle' });
    const title = await page.title();
    if (!title) throw new Error('Page title is empty');
    if (!title.includes('LLM')) throw new Error(`Title does not contain "LLM": "${title}"`);
  });

  await test('Login form has username and password inputs', async () => {
    const inputCount = await page.evaluate(() => document.querySelectorAll('input').length);
    if (inputCount < 2) throw new Error(`Expected at least 2 inputs, found ${inputCount}`);
    // Check for visible input fields
    const visibleInputs = await page.evaluate(() =>
      Array.from(document.querySelectorAll('input:not([type="hidden"])')).length
    );
    if (visibleInputs < 2) throw new Error(`Expected at least 2 visible inputs, found ${visibleInputs}`);
  });

  await test('Login page shows LLM platform branding', async () => {
    const bodyText = await page.textContent('body');
    if (!bodyText.includes('LLM 平台') && !bodyText.includes('LLM')) {
      throw new Error('Branding text not found on login page');
    }
  });

  await test('Particle canvas background exists on login page', async () => {
    const hasCanvas = await page.evaluate(() => !!document.querySelector('canvas'));
    if (!hasCanvas) throw new Error('Canvas particle background not found');
  });

  await test('Login page has login button', async () => {
    const btnText = await page.evaluate(() => {
      const btn = document.querySelector('button[type="submit"]');
      return btn ? btn.textContent : '';
    });
    if (!btnText || (!btnText.includes('登') && !btnText.includes('录'))) {
      throw new Error('Login button not found');
    }
  });

  await test('Successful login with admin/admin redirects to dashboard', async () => {
    // Fill credentials
    const inputs = await page.$$('input');
    if (inputs.length < 2) throw new Error('Not enough input fields');
    await inputs[0].fill('admin');
    await inputs[1].fill('admin');
    // Click submit
    await page.click('button[type="submit"]');
    try {
      await page.waitForURL('**/dashboard', { timeout: 10000 });
    } catch {
      throw new Error(`Login did not redirect to dashboard. Current URL: ${page.url()}`);
    }
  });

  await test('After login, header shows user info', async () => {
    const headerOk = await page.evaluate(() => {
      const header = document.querySelector('.ant-layout-header, header');
      if (!header) return false;
      // Header should contain user-related text (e.g. username, avatar, dropdown)
      return header.textContent.length > 0;
    });
    if (!headerOk) throw new Error('Header bar not visible or empty after login');
  });

  // =========================================================================
  // 2. DASHBOARD DATA DISPLAY
  // =========================================================================
  section('2. DASHBOARD DATA DISPLAY');

  await test('Dashboard loads with statistics cards', async () => {
    await page.goto(`${BASE}/dashboard`, { timeout: 10000, waitUntil: 'networkidle' });
    // Wait for Ant Design Statistic components to render
    await page.waitForTimeout(2000);
    const bodyText = await page.textContent('body');
    if (!bodyText.includes('Token') && !bodyText.includes('费') && !bodyText.includes('模型')) {
      // Check for Ant Statistic values
      const statValues = await page.evaluate(() =>
        Array.from(document.querySelectorAll('.ant-statistic-content-value')).map((el) => el.textContent)
      );
      if (statValues.length === 0) throw new Error('No statistics cards rendered on dashboard');
    }
  });

  await test('Dashboard has Token usage statistic', async () => {
    const bodyText = await page.textContent('body');
    if (!bodyText.includes('Token')) throw new Error('Token stat not found on dashboard');
  });

  await test('Dashboard has cost statistic', async () => {
    const bodyText = await page.textContent('body');
    if (!bodyText.includes('费') && !bodyText.includes('Cost') && !bodyText.includes('$')) {
      throw new Error('Cost stat not found on dashboard');
    }
  });

  await test('Dashboard has health status indicator', async () => {
    const bodyText = await page.textContent('body');
    if (!bodyText.includes('健康') && !bodyText.includes('Healthy')) {
      throw new Error('Health status not found on dashboard');
    }
  });

  // =========================================================================
  // 3. ALL 6 PAGES + 3 ADMIN SUB-PAGES NAVIGATION
  // =========================================================================
  section('3. PAGE NAVIGATION (6 main pages)');

  const mainPages = [
    { path: '/rag', name: 'RAG Knowledge Base', heading: 'RAG' },
    { path: '/agent', name: 'Agent Console', heading: 'Agent' },
    { path: '/prompts', name: 'Prompt Engineering', heading: 'Prompt' },
    { path: '/gateway', name: 'Gateway Monitor', heading: 'Gateway' },
    { path: '/mcp', name: 'MCP Management', heading: 'MCP' },
    { path: '/admin', name: 'Admin Panel', heading: '管理' },
  ];

  for (const { path, name } of mainPages) {
    await test(`Navigate to ${path} (${name})`, async () => {
      await page.goto(`${BASE}${path}`, { timeout: 15000, waitUntil: 'networkidle' });
      await page.waitForTimeout(1500); // Allow lazy-loaded components to render
      const url = page.url();
      if (url.includes('/login')) throw new Error(`Redirected to login from ${path}`);
      // Verify page rendered (not blank)
      const hasContent = await page.evaluate(() => document.body.textContent.length > 50);
      if (!hasContent) throw new Error(`Page ${path} appears blank`);
    });
  }

  section('3b. ADMIN SUB-PAGES NAVIGATION');

  const adminSubPages = [
    { path: '/admin', tab: '概览' },
    { path: '/admin/tenants', tab: '租户' },
    { path: '/admin/audit', tab: '审计日志' },
    { path: '/admin/keys', tab: 'API Keys' },
  ];

  for (const { path, tab } of adminSubPages) {
    await test(`Navigate to ${path} (${tab})`, async () => {
      await page.goto(`${BASE}${path}`, { timeout: 15000, waitUntil: 'networkidle' });
      await page.waitForTimeout(1500);
      const url = page.url();
      if (url.includes('/login')) throw new Error(`Redirected to login from ${path}`);
      if (url.includes('/dashboard') && path !== '/admin') {
        throw new Error(`Redirected to dashboard from ${path}`);
      }
    });
  }

  // =========================================================================
  // 4. RAG PAGE: SEARCH FORM & UPLOAD TAB WITH DRAG AREA
  // =========================================================================
  section('4. RAG PAGE');

  await test('RAG page shows title "RAG 知识库"', async () => {
    await page.goto(`${BASE}/rag`, { timeout: 10000, waitUntil: 'networkidle' });
    await page.waitForTimeout(1500);
    const bodyText = await page.textContent('body');
    if (!bodyText.includes('RAG') && !bodyText.includes('知识库')) {
      throw new Error('RAG page title not found');
    }
  });

  await test('RAG page has Search tab with query input', async () => {
    // The search tab should be active by default
    const hasTextArea = await page.evaluate(() => {
      return !!document.querySelector('textarea') || !!document.querySelector('.ant-input');
    });
    if (!hasTextArea) throw new Error('Search query input not found');
  });

  await test('RAG page has search button', async () => {
    const bodyText = await page.textContent('body');
    if (!bodyText.includes('搜索')) throw new Error('Search button not found on RAG page');
  });

  await test('RAG page has collection selector', async () => {
    const hasSelect = await page.evaluate(() =>
      !!document.querySelector('.ant-select')
    );
    if (!hasSelect) throw new Error('Collection selector not found on RAG page');
  });

  await test('RAG page has upload tab with drag-and-drop area', async () => {
    // Click on the "上传" tab
    const uploadTab = await page.evaluateHandle(() => {
      const tabs = Array.from(document.querySelectorAll('.ant-tabs-tab'));
      const tab = tabs.find((t) => t.textContent.includes('上传'));
      return tab || null;
    });
    if (!uploadTab) throw new Error('Upload tab not found');
    await uploadTab.click();
    await page.waitForTimeout(800);
    // Check for drag area
    const hasDragArea = await page.evaluate(() => {
      return !!document.querySelector('.ant-upload-drag') ||
             !!document.querySelector('.ant-upload');
    });
    if (!hasDragArea) throw new Error('Drag-and-drop upload area not found');
  });

  await test('RAG upload tab shows accepted file types hint', async () => {
    const bodyText = await page.textContent('body');
    if (!bodyText.includes('PDF') && !bodyText.includes('拖拽')) {
      throw new Error('File type hints not found in upload tab');
    }
  });

  await test('RAG page has Documents tab with table', async () => {
    const docsTab = await page.evaluateHandle(() => {
      const tabs = Array.from(document.querySelectorAll('.ant-tabs-tab'));
      const tab = tabs.find((t) => t.textContent.includes('文档'));
      return tab || null;
    });
    if (!docsTab) throw new Error('Documents tab not found');
    await docsTab.click();
    await page.waitForTimeout(800);
    const hasTable = await page.evaluate(() => !!document.querySelector('.ant-table'));
    // Table may show empty state, that's ok
    const bodyText = await page.textContent('body');
    if (!bodyText.includes('文件名') && !bodyText.includes('暂无')) {
      throw new Error('Documents table or empty state not found');
    }
  });

  // =========================================================================
  // 5. AGENT PAGE: AGENT TYPE SELECTOR, TASK INPUT, RUN BUTTON
  // =========================================================================
  section('5. AGENT PAGE');

  await test('Agent page loads with title "Agent 运行器"', async () => {
    await page.goto(`${BASE}/agent`, { timeout: 10000, waitUntil: 'networkidle' });
    await page.waitForTimeout(1500);
    const bodyText = await page.textContent('body');
    if (!bodyText.includes('Agent')) throw new Error('Agent page title not found');
  });

  await test('Agent page has agent type selector', async () => {
    const selectCount = await page.evaluate(() =>
      document.querySelectorAll('.ant-select').length
    );
    if (selectCount < 1) throw new Error('Agent type selector not found');
  });

  await test('Agent page has model selector', async () => {
    const selectCount = await page.evaluate(() =>
      document.querySelectorAll('.ant-select').length
    );
    if (selectCount < 2) throw new Error('Model selector not found (expected at least 2 selects)');
  });

  await test('Agent page has task description input (textarea)', async () => {
    const hasTextArea = await page.evaluate(() => !!document.querySelector('textarea'));
    if (!hasTextArea) throw new Error('Task input textarea not found');
  });

  await test('Agent page has "运行 Agent" run button', async () => {
    const bodyText = await page.textContent('body');
    if (!bodyText.includes('运行')) throw new Error('Run button not found');
  });

  await test('Agent page run button is disabled when input is empty', async () => {
    const isDisabled = await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const runBtn = buttons.find((b) => b.textContent.includes('运行'));
      return runBtn ? runBtn.disabled : null;
    });
    // Button should be disabled or not found
    if (isDisabled === false) throw new Error('Run button should be disabled when no input');
  });

  await test('Agent page shows placeholder text when no result', async () => {
    const bodyText = await page.textContent('body');
    if (!bodyText.includes('配置') && !bodyText.includes('Agent')) {
      throw new Error('Placeholder/empty state not found');
    }
  });

  // =========================================================================
  // 6. PROMPTS PAGE: TEMPLATE LIST, EDITOR TAB
  // =========================================================================
  section('6. PROMPTS PAGE');

  await test('Prompts page loads with title "Prompt 工程"', async () => {
    await page.goto(`${BASE}/prompts`, { timeout: 10000, waitUntil: 'networkidle' });
    await page.waitForTimeout(1500);
    const bodyText = await page.textContent('body');
    if (!bodyText.includes('Prompt')) throw new Error('Prompts page title not found');
  });

  await test('Prompts page has template list sidebar', async () => {
    const bodyText = await page.textContent('body');
    if (!bodyText.includes('模板')) throw new Error('Template list sidebar not found');
  });

  await test('Prompts page has "新建" (create) button', async () => {
    const bodyText = await page.textContent('body');
    if (!bodyText.includes('新建')) throw new Error('Create template button not found');
  });

  await test('Prompts page shows empty state when no template selected', async () => {
    const bodyText = await page.textContent('body');
    if (!bodyText.includes('选择') && !bodyText.includes('暂无模板')) {
      throw new Error('Empty state message not found when no template selected');
    }
  });

  await test('Prompts page shows create form when "新建" is clicked', async () => {
    const createBtn = await page.evaluateHandle(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      return buttons.find((b) => b.textContent.includes('新建')) || null;
    });
    if (!createBtn) throw new Error('Create button not found');
    await createBtn.click();
    await page.waitForTimeout(500);
    const bodyText = await page.textContent('body');
    if (!bodyText.includes('模板名称') && !bodyText.includes('创建')) {
      throw new Error('Create template form did not appear');
    }
  });

  // =========================================================================
  // 7. GATEWAY PAGE: PROVIDER CARDS VISIBLE
  // =========================================================================
  section('7. GATEWAY PAGE');

  await test('Gateway page loads with title', async () => {
    await page.goto(`${BASE}/gateway`, { timeout: 10000, waitUntil: 'networkidle' });
    await page.waitForTimeout(2000); // Extra time for mock data loading
    const bodyText = await page.textContent('body');
    if (!bodyText.includes('Gateway') && !bodyText.includes('网关')) {
      throw new Error('Gateway page title not found');
    }
  });

  await test('Gateway page shows guidance when no data', async () => {
    const bodyText = await page.textContent('body');
    // No real backend providers → empty/guidance state
    if (!bodyText.includes('无法获取')) {
      throw new Error('Gateway empty state guidance not found');
    }
  });


  await test('Gateway page has circuit breaker status section', async () => {
    const bodyText = await page.textContent('body');
    if (!bodyText.includes('断路器')) throw new Error('Circuit breaker section not found');
  });

  // =========================================================================
  // 8. MCP PAGE: SERVER TABLE EXISTS
  // =========================================================================
  section('8. MCP PAGE');

  await test('MCP page loads with title "MCP 服务器"', async () => {
    await page.goto(`${BASE}/mcp`, { timeout: 10000, waitUntil: 'networkidle' });
    await page.waitForTimeout(1500);
    const bodyText = await page.textContent('body');
    if (!bodyText.includes('MCP')) throw new Error('MCP page title not found');
  });

  await test('MCP page has "添加服务器" (add server) button', async () => {
    const bodyText = await page.textContent('body');
    if (!bodyText.includes('添加服务器') && !bodyText.includes('添加')) {
      throw new Error('Add server button not found');
    }
  });

  await test('MCP page has empty state or table', async () => {
    const bodyText = await page.textContent('body');
    const hasTable = bodyText.includes('服务器名称') || bodyText.includes('名称');
    const hasEmpty = bodyText.includes('暂无') || bodyText.includes('未配置') || bodyText.includes('第一个');
    if (!hasTable && !hasEmpty) {
      // Maybe there's data loaded (spin finished)
      const hasSpin = await page.evaluate(() => !!document.querySelector('.ant-spin'));
      if (hasSpin) throw new Error('Page still loading (spinner visible)');
    }
  });

  await test('MCP page "添加服务器" opens drawer with form', async () => {
    const addBtn = await page.evaluateHandle(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      return buttons.find((b) => b.textContent.includes('添加服务器') || b.textContent.includes('添加')) || null;
    });
    if (!addBtn) throw new Error('Add server button not found');
    await addBtn.click();
    await page.waitForTimeout(800);
    const drawerVisible = await page.evaluate(() => {
      return !!document.querySelector('.ant-drawer') || !!document.querySelector('.ant-drawer-open');
    });
    if (!drawerVisible) throw new Error('Add server drawer did not open');
  });

  await test('MCP drawer has name and command fields', async () => {
    const bodyText = await page.textContent('body');
    if (!bodyText.includes('服务器名称') && !bodyText.includes('命令')) {
      throw new Error('Drawer form fields not found');
    }
  });

  // Close drawer
  await test('MCP drawer can be closed', async () => {
    const closeBtn = await page.evaluateHandle(() => {
      const buttons = Array.from(document.querySelectorAll('.ant-drawer button'));
      return buttons.find((b) => b.textContent.includes('取消') || b.getAttribute('aria-label') === 'Close') || null;
    });
    if (closeBtn) {
      await closeBtn.click();
      await page.waitForTimeout(500);
    }
    // Press Escape as fallback
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);
  });

  // =========================================================================
  // 9. ADMIN PAGE: TENANTS, AUDIT LOGS, USAGE REPORT (OVERVIEW)
  // =========================================================================
  section('9. ADMIN PAGE');

  await test('Admin overview shows statistics cards', async () => {
    await page.goto(`${BASE}/admin`, { timeout: 15000, waitUntil: 'networkidle' });
    await page.waitForTimeout(2000);
    const bodyText = await page.textContent('body');
    if (!bodyText.includes('管理面板')) throw new Error('Admin page title not found');
    // Check for overview stats
    const hasStats = ['用户总数', '租户', 'API 请求', 'API Keys'].some((s) => bodyText.includes(s));
    if (!hasStats) throw new Error('Admin overview stats not found');
  });

  await test('Admin overview shows system health section', async () => {
    const bodyText = await page.textContent('body');
    if (!bodyText.includes('系统健康') && !bodyText.includes('正常运行')) {
      throw new Error('System health section not found');
    }
  });

  await test('Admin tenants tab shows tenant table', async () => {
    // Click the tenants tab
    const tenantsTab = await page.evaluateHandle(() => {
      const tabs = Array.from(document.querySelectorAll('.ant-tabs-tab'));
      return tabs.find((t) => t.textContent.includes('租户')) || null;
    });
    if (!tenantsTab) throw new Error('Tenants tab not found');
    await tenantsTab.click();
    await page.waitForTimeout(1000);
    const bodyText = await page.textContent('body');
    if (!bodyText.includes('名称') && !bodyText.includes('等级')) {
      throw new Error('Tenant table columns not found');
    }
  });

  await test('Admin tenants tab has "添加租户" button', async () => {
    const bodyText = await page.textContent('body');
    if (!bodyText.includes('添加租户')) throw new Error('Add tenant button not found');
  });

  await test('Admin audit log tab shows filter controls', async () => {
    const auditTab = await page.evaluateHandle(() => {
      const tabs = Array.from(document.querySelectorAll('.ant-tabs-tab'));
      return tabs.find((t) => t.textContent.includes('审计日志')) || null;
    });
    if (!auditTab) throw new Error('Audit log tab not found');
    await auditTab.click();
    await page.waitForTimeout(1000);
    const bodyText = await page.textContent('body');
    if (!bodyText.includes('审计')) throw new Error('Audit log tab not visible');
    // Check for filter elements
    const hasFilters = bodyText.includes('用户') || bodyText.includes('操作') || bodyText.includes('搜索');
    if (!hasFilters) throw new Error('Audit log filters not found');
  });

  await test('Admin audit log has date picker filter', async () => {
    const hasRangePicker = await page.evaluate(() => {
      return !!document.querySelector('.ant-picker-range') ||
             document.querySelectorAll('.ant-picker').length >= 2;
    });
    if (!hasRangePicker) throw new Error('Date range picker not found in audit log');
  });

  // =========================================================================
  // 10. ADMIN API KEYS: FULL CRUD FLOW
  // =========================================================================
  section('10. ADMIN API KEYS');

  let trackedKeyName = 'e2e-test-key-' + Date.now();

  await test('Navigate to API Keys tab and verify table exists', async () => {
    await page.goto(`${BASE}/admin/keys`, { timeout: 15000, waitUntil: 'networkidle' });
    await page.waitForTimeout(2000);
    const bodyText = await page.textContent('body');
    // Check for the API Keys table content
    if (!bodyText.includes('API Keys') && !bodyText.includes('生产') && !bodyText.includes('开发')) {
      throw new Error('API Keys table not found');
    }
  });

  await test('API Keys tab has "生成 Key" button', async () => {
    const bodyText = await page.textContent('body');
    if (!bodyText.includes('生成')) {
      throw new Error('Generate key button not found');
    }
  });

  await test('API Keys table shows key name column', async () => {
    const bodyText = await page.textContent('body');
    if (!bodyText.includes('名称')) throw new Error('Key name column not found in table');
  });

  await test('API Keys table shows key status column', async () => {
    const bodyText = await page.textContent('body');
    // Check for status indicators
    if (!bodyText.includes('状态')) throw new Error('Status column not found');
  });

  await test('API Keys page has generate button', async () => {
    const bodyText = await page.textContent('body');
    if (!bodyText.includes('生成')) throw new Error('Generate key button not found');
  });

  await test('API Keys table starts empty', async () => {
    const bodyText = await page.textContent('body');
    // No fake keys → table should show empty state
    const hasEmpty = bodyText.includes('暂无') || bodyText.includes('暂无数据');
    const hasNoRows = await page.evaluate(() => {
      const rows = document.querySelectorAll('.ant-table-tbody tr.ant-table-row');
      return rows.length === 0;
    });
    if (!hasEmpty && !hasNoRows) {
      throw new Error('API Keys table should be empty (no pre-populated rows)');
    }
  });

  // =========================================================================
  // 11. CHECK CHINESE TEXT ON ALL PAGES
  // =========================================================================
  section('11. CHINESE TEXT VERIFICATION');

  const chineseCheckPages = [
    { path: '/dashboard', name: 'Dashboard' },
    { path: '/rag', name: 'RAG' },
    { path: '/agent', name: 'Agent' },
    { path: '/prompts', name: 'Prompts' },
    { path: '/gateway', name: 'Gateway' },
    { path: '/mcp', name: 'MCP' },
    { path: '/admin', name: 'Admin Overview' },
    { path: '/admin/tenants', name: 'Admin Tenants' },
    { path: '/admin/audit', name: 'Admin Audit' },
    { path: '/admin/keys', name: 'Admin Keys' },
  ];

  for (const { path, name } of chineseCheckPages) {
    await test(`[i18n] ${name} page uses Chinese labels (no raw English UI strings)`, async () => {
      await page.goto(`${BASE}${path}`, { timeout: 15000, waitUntil: 'networkidle' });
      await page.waitForTimeout(1500);
      const bodyText = await page.textContent('body');

      // Must have Chinese characters in UI labels
      if (!hasChinese(bodyText)) {
        throw new Error(`Page "${name}" has no Chinese text at all`);
      }

      // Check for suspicious English UI labels
      const suspicious = hasSuspiciousEnglish(bodyText);
      if (suspicious) {
        throw new Error(`Page "${name}" contains English UI label: "${suspicious}"`);
      }
    });
  }

  await test('[i18n] Login page uses Chinese labels', async () => {
    await page.goto(`${BASE}/login`, { timeout: 15000, waitUntil: 'networkidle' });
    await page.waitForTimeout(1000);
    const bodyText = await page.textContent('body');
    // Must have Chinese labels on the login page
    if (!bodyText.includes('平台') && !bodyText.includes('用户名')) {
      throw new Error('Login page lacks Chinese labels');
    }
    if (bodyText.match(/\bLogin\b(?!\s*(?:平台|页面|系统))/)) {
      throw new Error('Login page has English "Login" text without Chinese context');
    }
  });

  // =========================================================================
  // 12. SIDEBAR COLLAPSE / EXPAND
  // =========================================================================
  section('12. SIDEBAR COLLAPSE / EXPAND');

  await test('Sidebar is initially expanded', async () => {
    await page.goto(`${BASE}/dashboard`, { timeout: 10000, waitUntil: 'networkidle' });
    await page.waitForTimeout(1500);
    const sidebarWidth = await page.evaluate(() => {
      const sider = document.querySelector('.ant-layout-sider');
      if (!sider) return null;
      return sider.clientWidth;
    });
    if (sidebarWidth !== null && sidebarWidth < 100) {
      throw new Error(`Sidebar appears collapsed (width: ${sidebarWidth}px)`);
    }
  });

  await test('Sidebar shows all navigation menu items when expanded', async () => {
    const menuItems = await page.evaluate(() => {
      return Array.from(document.querySelectorAll('.ant-menu-item'))
        .map((el) => el.textContent.trim())
        .filter(Boolean);
    });
    // Should have many menu items
    if (menuItems.length < 5) {
      throw new Error(`Expected at least 5 menu items, found ${menuItems.length}: ${menuItems.join(', ')}`);
    }
  });

  await test('Sidebar shows platform name "LLM 平台" when expanded', async () => {
    const bodyText = await page.textContent('body');
    if (!bodyText.includes('LLM 平台')) throw new Error('Platform name not visible in expanded sidebar');
  });

  await test('Sidebar collapse button exists (header toggle)', async () => {
    // The toggle button is in the Header, not the Sidebar
    const toggleExists = await page.evaluate(() => {
      // Find the collapse toggle button - it's in the header with menu fold/unfold icon
      const header = document.querySelector('.ant-layout-header, header');
      if (!header) return false;
      return header.querySelectorAll('button').length > 0;
    });
    if (!toggleExists) throw new Error('Sidebar collapse toggle button not found');
  });

  await test('Clicking toggle collapses the sidebar', async () => {
    // Find the toggle button in the header (first button, typically)
    const toggleBtn = await page.evaluateHandle(() => {
      const header = document.querySelector('.ant-layout-header, header');
      if (!header) return null;
      const buttons = header.querySelectorAll('button');
      // The first button in the header is usually the sidebar toggle
      return buttons[0] || null;
    });
    if (!toggleBtn) throw new Error('Toggle button not found');
    await toggleBtn.click();
    await page.waitForTimeout(800);
    // Check sidebar width after collapse
    const sidebarWidth = await page.evaluate(() => {
      const sider = document.querySelector('.ant-layout-sider');
      if (!sider) return null;
      return sider.clientWidth;
    });
    if (sidebarWidth !== null && sidebarWidth > 100) {
      throw new Error(`Sidebar did not collapse (width: ${sidebarWidth}px, expected < 100)`);
    }
  });

  await test('Platform name is hidden when sidebar is collapsed', async () => {
    const hasPlatformName = await page.evaluate(() => {
      const sider = document.querySelector('.ant-layout-sider');
      if (!sider) return true; // can't check
      return sider.textContent.includes('LLM 平台');
    });
    if (hasPlatformName) throw new Error('Platform name still visible after collapse');
  });

  await test('Clicking toggle again expands the sidebar', async () => {
    const toggleBtn = await page.evaluateHandle(() => {
      const header = document.querySelector('.ant-layout-header, header');
      if (!header) return null;
      const buttons = header.querySelectorAll('button');
      return buttons[0] || null;
    });
    if (!toggleBtn) throw new Error('Toggle button not found');
    await toggleBtn.click();
    await page.waitForTimeout(800);
    const sidebarWidth = await page.evaluate(() => {
      const sider = document.querySelector('.ant-layout-sider');
      if (!sider) return null;
      return sider.clientWidth;
    });
    if (sidebarWidth !== null && sidebarWidth < 100) {
      throw new Error(`Sidebar did not re-expand (width: ${sidebarWidth}px)`);
    }
  });

  // =========================================================================
  // SUMMARY
  // =========================================================================
  section('SUMMARY');

  console.log(`\n  Total : ${results.length}`);
  console.log(`  Passed: ${passed}`);
  console.log(`  Failed: ${failed}`);
  console.log(`  Rate  : ${((passed / results.length) * 100).toFixed(1)}%`);

  if (failed > 0) {
    console.log(`\n  Failed tests:`);
    for (const r of results) {
      if (r.status === 'FAIL') {
        console.log(`    - ${r.name}: ${r.error}`);
      }
    }
  }

  console.log(`\n${'='.repeat(60)}`);
  console.log(`  E2E COMPLETE`);
  console.log(`${'='.repeat(60)}\n`);

  await browser.close();

  // Exit with appropriate code
  process.exit(failed > 0 ? 1 : 0);
})();
