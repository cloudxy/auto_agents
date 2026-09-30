// Read-only UI evidence capture on the running local build (manager, 2026-09-27).
// Navigates only; never clicks mutating controls. Records console errors, page errors and API responses >= 400.
const { chromium } = require('/Users/xuyun/auto_agents/node_modules/playwright');
const fs = require('fs');
const OUT = process.argv[2];
const ADMIN = 'http://127.0.0.1:9112', OFFICIAL = 'http://127.0.0.1:9113';
const officialPages = ['/', '/pricing', '/register', '/skills', '/capabilities', '/terms', '/privacy', '/no-such-page'];
const adminPages = ['/dashboard','/spiders/tasks','/spiders/logs','/spiders/nodes','/ai','/enterprise','/rbac','/capabilities','/capabilities/installs','/members','/usage','/billing/checkout','/pricing','/relay','/outbound-keys','/llm','/payment-credentials','/logs','/data','/newapi','/platform-ops','/users','/settings'];
const report = [];
function hook(page, rec) {
  page.on('console', m => { if (m.type() === 'error') rec.console.push(m.text().slice(0, 300)); });
  page.on('pageerror', e => rec.pageerrors.push(String(e).slice(0, 300)));
  page.on('response', r => { const u = r.url(); if (u.includes('/api/') && r.status() >= 400) rec.http.push(`${r.status()} ${r.request().method()} ${u.replace(/^https?:\/\/[^/]+/, '')}`); });
}
async function shot(ctx, base, path, tag, widths) {
  const page = await ctx.newPage();
  const rec = { app: tag, path, console: [], pageerrors: [], http: [], title: '', ms: 0 };
  hook(page, rec);
  const t0 = Date.now();
  try {
    await page.goto(base + path, { waitUntil: 'networkidle', timeout: 30000 });
  } catch (e) { rec.pageerrors.push('goto: ' + String(e).slice(0, 200)); }
  await page.waitForTimeout(1200);
  rec.ms = Date.now() - t0; rec.title = await page.title().catch(() => '');
  rec.finalUrl = page.url().replace(/^https?:\/\/[^/]+/, '');
  const name = `${tag}${path.replace(/\//g, '_') || '_root'}`;
  for (const w of widths) {
    await page.setViewportSize({ width: w, height: w < 500 ? 812 : 900 });
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${OUT}/${name}-${w}.png`, fullPage: w >= 1000 });
  }
  report.push(rec); await page.close();
}
(async () => {
  const browser = await chromium.launch();
  const off = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  if (!process.env.SKIP_OFFICIAL) for (const p of officialPages) await shot(off, OFFICIAL, p, 'official', [1440, 375]);
  const adm = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const lp = await adm.newPage();
  const lrec = { app: 'admin', path: '/login', console: [], pageerrors: [], http: [] }; hook(lp, lrec);
  await lp.goto(ADMIN + '/login', { waitUntil: 'networkidle' });
  await lp.screenshot({ path: `${OUT}/admin_login-1440.png` });
  await lp.setViewportSize({ width: 375, height: 812 }); await lp.screenshot({ path: `${OUT}/admin_login-375.png` }); await lp.setViewportSize({ width: 1440, height: 900 });
  const inputs = lp.locator('input');
  await inputs.nth(0).fill('admin'); await lp.locator('input[type=password]').fill('123456');
  const cb = lp.locator('input[type=checkbox]'); if (await cb.count()) await cb.first().check().catch(()=>{});
  await lp.keyboard.press('Enter');
  await lp.waitForTimeout(3000);
  lrec.finalUrl = lp.url(); report.push(lrec); await lp.close();
  if (!String(lrec.finalUrl).includes('/login')) {
    for (const p of adminPages) await shot(adm, ADMIN, p, 'admin', p === '/dashboard' || p === '/spiders/tasks' || p === '/usage' ? [1440, 375] : [1440]);
  } else { report.push({ app: 'admin', path: 'LOGIN_FAILED', console: [], pageerrors: [], http: [] }); }
  fs.writeFileSync(`${OUT}/../ui-capture-report${process.env.SKIP_OFFICIAL ? '-admin' : ''}.json`, JSON.stringify(report, null, 2));
  await browser.close();
  for (const r of report) console.log(`${r.app}${r.path} -> ${r.finalUrl || ''} ms=${r.ms || ''} http=${r.http.length} console=${r.console.length} pageerr=${r.pageerrors.length}`);
})();
