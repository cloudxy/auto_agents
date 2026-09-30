// Read-only re-capture (manager, 2026-09-28): official home with reduced motion; admin dashboard with extra wait + bar count.
const { chromium } = require('/Users/xuyun/auto_agents/node_modules/playwright');
const OUT = process.argv[2];
(async () => {
  const b = await chromium.launch();
  const off = await b.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
  const p = await off.newPage();
  await p.goto('http://127.0.0.1:9113/', { waitUntil: 'networkidle' }); await p.waitForTimeout(1500);
  await p.screenshot({ path: `${OUT}/official_home_reducedmotion-1440.png`, fullPage: true });
  await p.setViewportSize({ width: 375, height: 812 }); await p.waitForTimeout(500);
  await p.screenshot({ path: `${OUT}/official_home_reducedmotion-375.png`, fullPage: true });
  const adm = await b.newContext({ viewport: { width: 1440, height: 900 } });
  const a = await adm.newPage();
  await a.goto('http://127.0.0.1:9112/login', { waitUntil: 'networkidle' });
  await a.locator('input').nth(0).fill('admin'); await a.locator('input[type=password]').fill('123456');
  await a.keyboard.press('Enter'); await a.waitForURL('**/dashboard', { timeout: 15000 });
  await a.waitForLoadState('networkidle'); await a.waitForTimeout(3000);
  const bars = await a.evaluate(() => document.querySelectorAll('.recharts-bar-rectangle').length);
  const sw = await a.evaluate(() => document.documentElement.scrollWidth);
  await a.screenshot({ path: `${OUT}/admin_dashboard_wait3s-1440.png`, fullPage: true });
  await a.setViewportSize({ width: 375, height: 812 }); await a.waitForTimeout(800);
  const sw375 = await a.evaluate(() => document.documentElement.scrollWidth);
  console.log(`dashboard recharts-bar-rectangle=${bars} scrollWidth@1440=${sw} scrollWidth@375=${sw375}`);
  await b.close();
})();
