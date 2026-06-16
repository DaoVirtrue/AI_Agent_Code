#!/bin/sh
docker rm -f pw-test 2>/dev/null
docker run -d --name pw-test --network llm-platform_llm-platform-net mcr.microsoft.com/playwright:latest sleep 600
sleep 2

echo "=== Install ==="
docker exec pw-test bash -c "cd /tmp && npm init -y --silent && npm install playwright 2>&1 | tail -2"

echo "=== Test ==="
cat << 'SCRIPT_END' > /tmp/pw.js
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const logs = [];
  page.on('console', msg => logs.push(msg.type() + ': ' + msg.text()));
  page.on('pageerror', err => logs.push('ERR: ' + err.message));
  try {
    await page.goto('http://llm-platform-frontend/login', { timeout: 20000, waitUntil: 'networkidle' });
    console.log('Title:', await page.title());
    console.log('URL:', page.url());
    const body = await page.textContent('body');
    console.log('Body:', (body || '').substring(0, 400));
    console.log('Canvas count:', await page.evaluate(() => document.querySelectorAll('canvas').length));
    console.log('Input count:', await page.evaluate(() => document.querySelectorAll('input').length));
    const btnTexts = await page.evaluate(() => Array.from(document.querySelectorAll('button')).map(b => b.textContent.trim()));
    console.log('Buttons:', JSON.stringify(btnTexts));

    const inputs = await page.evaluate(() => Array.from(document.querySelectorAll('input')).map(i => i.getAttribute('placeholder') || i.type));
    console.log('Input details:', JSON.stringify(inputs));

    // Fill form and click login
    const inputElements = await page.evaluateHandle(() => document.querySelectorAll('input'));
    const count = await inputElements.evaluate(els => els.length);
    console.log('Input count (handle):', count);
    if (count >= 2) {
      const allInputs = await page.evaluateHandle(() => document.querySelectorAll('input'));
      await allInputs.evaluate((els) => { els[0].value = 'admin'; els[1].value = 'admin'; });
      const submitBtn = await page.evaluateHandle(() => document.querySelector('button[type="submit"]'));
      if (submitBtn) {
        await submitBtn.click();
        await page.waitForTimeout(3000);
        console.log('After login URL:', page.url());
        console.log('After login Title:', await page.title());
        const newBody = await page.textContent('body');
        console.log('After login Body:', (newBody || '').substring(0, 300));
      }
    }

    // Navigate to dashboard
    await page.goto('http://llm-platform-frontend/dashboard', { timeout: 10000, waitUntil: 'networkidle' });
    console.log('Dashboard URL:', page.url());
    console.log('Dashboard Title:', await page.title());

  } catch(e) { console.log('ERROR:', e.message); }
  console.log('---Logs---'); logs.forEach(l => console.log(l));
  await browser.close();
})();
SCRIPT_END

docker cp /tmp/pw.js pw-test:/tmp/pw.js
docker exec pw-test node /tmp/pw.js 2>&1
docker rm -f pw-test 2>/dev/null
