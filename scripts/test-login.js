const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  const logs = [];
  page.on('console', msg => logs.push(`[${msg.type()}] ${msg.text()}`));
  page.on('pageerror', err => logs.push(`[ERROR] ${err.message}`));

  try {
    console.log('=== Navigating to login ===');
    await page.goto('http://llm-platform-frontend/login', {
      timeout: 15000,
      waitUntil: 'networkidle'
    });

    console.log('Title:', await page.title());

    // Check for particles canvas
    const canvas = await page.$('canvas');
    console.log('Particles canvas found:', !!canvas);
    if (canvas) {
      const box = await canvas.boundingBox();
      console.log('Canvas size:', box);
    }

    // Check for visible text
    const bodyText = await page.textContent('body');
    console.log('Body preview:', bodyText.substring(0, 500));

    // Check for login form
    const inputCount = await page.$$eval('input', els => els.length);
    console.log('Input fields:', inputCount);

    const buttonText = await page.$$eval('button', els => els.map(e => e.textContent));
    console.log('Buttons:', buttonText);

    // Try logging in
    await page.fill('input[placeholder*="用户名"]', 'admin');
    await page.fill('input[placeholder*="密码"]', 'admin');
    await page.click('button[type="submit"]');
    await page.waitForTimeout(2000);

    const currentUrl = page.url();
    console.log('After login URL:', currentUrl);
    console.log('After login title:', await page.title());

    // Take screenshot
    await page.screenshot({ path: '/tmp/login.png', fullPage: true });
    console.log('Screenshot saved');

  } catch(e) {
    console.log('Error:', e.message);
    await page.screenshot({ path: '/tmp/error.png' });
  }

  console.log('\n=== Console logs ===');
  logs.forEach(l => console.log(l));

  await browser.close();
})();
