const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ headless: true });
  const p = await b.newPage();
  const logs = [];
  p.on('console', msg => logs.push(msg.type() + ':' + msg.text()));
  p.on('pageerror', e => logs.push('ERR:' + e.message));
  try {
    await p.goto('http://llm-platform-frontend/login', { timeout: 20000, waitUntil: 'networkidle' });
    console.log('1.TITLE:', await p.title());
    console.log('2.CANVAS:', await p.evaluate(() => document.querySelectorAll('canvas').length));
    // Use proper input methods that trigger React onChange
    const inputEls = await p.$$('input');
    if (inputEls.length >= 2) {
      await inputEls[0].click(); await inputEls[0].fill('admin');
      await inputEls[1].click(); await inputEls[1].fill('admin');
      console.log('3.FILLED');
    }
    const btn = await p.$('button[type="submit"]');
    if (btn) { await btn.click(); console.log('4.CLICKED'); }
    try { await p.waitForURL('**/dashboard', { timeout: 8000 }); console.log('5.REDIRECTED to dashboard!'); }
    catch { console.log('5.NO_REDIRECT, url:', p.url()); }
    const body = await p.textContent('body');
    console.log('6.BODY:', (body||'').substring(0, 400));
  } catch(e) { console.log('CATCH:', e.message); }
  console.log('---CONSOLE---'); logs.forEach(l => console.log(l));
  await b.close();
})();
