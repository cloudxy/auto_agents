/**
 * 浏览器主路径：登录 → 仪表盘 → 用量 → 成员。
 * 接口由 page.route 拦截，不依赖本机 MySQL/Redis。
 */
import { test, expect, type Page } from '@playwright/test'

const envelope = (data: unknown) => ({
  success: true, code: 'SUCCESS', message: 'ok', data,
})

const PERMS = [
  'menu:dashboard', 'menu:usage', 'menu:members',
  'menu:spiders.tasks', 'menu:spiders.logs', 'menu:spiders.nodes',
  'menu:ai', 'menu:data', 'menu:skills', 'menu:logs',
  'btn:create',
]

async function stubApi(page: Page) {
  await page.route('**/api/v1/**', async (route) => {
    const req = route.request()
    const url = req.url()
    const method = req.method()
    const json = (data: unknown) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(envelope(data)),
    })

    if (url.includes('/auth/login') && method === 'POST') {
      return json({
        access_token: 'e2e-token', token_type: 'bearer',
        username: 'alice', is_admin: true, role: 'admin',
        tenant_id: 1, tenant_role: 'owner', is_platform_admin: false,
      })
    }
    if (url.includes('/auth/permissions')) {
      return json(PERMS)
    }
    if (url.includes('/auth/menus')) {
      return json([])
    }
    if (url.includes('/admin/stats')) {
      return json({
        total_tasks: 3, pending: 0, running: 0, completed: 3, failed: 0,
        avg_duration_seconds: 1.2, success_rate: 1, total_results: 10,
        daily_tasks: [], daily_results: [], top_spiders: [],
      })
    }
    if (url.includes('/spiders/tasks')) {
      return json({ items: [], total: 0 })
    }
    if (url.includes('/tenants/me/usage/by-member')) {
      return json([])
    }
    if (url.includes('/tenants/me/usage')) {
      return json({
        tenant_id: 1,
        quota: { task_concurrency: 5, result_storage: 10, llm_tokens_month: 100 },
        usage: { task_concurrency: 1, result_storage: 2, llm_tokens_month: 3 },
        llm_by_provider: {}, cost_by_provider: {}, cost_cents_total: 0,
      })
    }
    if (url.includes('/tenants/me/delivery-webhook')) {
      return json({ delivery_webhook_url: null })
    }
    if (url.includes('/billing/plans')) return json([])
    if (url.includes('/billing/subscription')) return json(null)
    if (url.includes('/billing/orders')) return json([])
    if (url.includes('/members/audit')) return json([])
    if (url.includes('/members')) {
      return json([
        { id: 1, username: 'alice', email: 'a@a.com', tenant_role: 'owner', is_active: true },
      ])
    }
    return json(null)
  })
}

test('login then dashboard usage members', async ({ page }) => {
  await stubApi(page)
  await page.goto('/login')
  await expect(page.getByPlaceholder('用户名')).toBeVisible()
  await page.getByPlaceholder('用户名').fill('alice')
  await page.getByPlaceholder('密码').fill('secret1')
  await page.getByRole('checkbox', { name: /记住我/ }).check()
  await page.getByRole('button', { name: /登\s*录/ }).click()

  await expect(page).toHaveURL(/\/dashboard/)
  await expect(page.getByText('任务总数')).toBeVisible({ timeout: 15_000 })

  await page.goto('/usage')
  await expect(page.getByText('任务并发')).toBeVisible()
  await expect(page.getByText(/任务结果推送/)).toBeVisible()

  await page.goto('/members')
  await expect(page.getByText(/企业内部事务/)).toBeVisible()
  await expect(page.getByRole('cell', { name: 'alice' })).toBeVisible()
})

// 审计 BUG-39 / B5-6：375 宽下主旅程页不横向溢出；侧栏收成抽屉，菜单能打开并导航
test('375px: no horizontal overflow, nav drawer works', async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 375, height: 812 } })
  const page = await ctx.newPage()
  await stubApi(page)
  await page.goto('/login')
  await page.getByPlaceholder('用户名').fill('alice')
  await page.getByPlaceholder('密码').fill('secret1')
  await page.getByRole('checkbox', { name: /记住我/ }).check()
  await page.getByRole('button', { name: /登\s*录/ }).click()
  await expect(page).toHaveURL(/\/dashboard/)

  for (const path of ['/dashboard', '/usage', '/members', '/spiders/tasks']) {
    await page.goto(path)
    await page.waitForLoadState('networkidle')
    const width = await page.evaluate(() => document.documentElement.scrollWidth)
    expect(width, `${path} scrollWidth`).toBeLessThanOrEqual(375)
  }

  await page.getByRole('button', { name: '打开菜单' }).click()
  const drawer = page.getByRole('dialog')
  await expect(drawer).toBeVisible()
  await drawer.getByText('概览').click()
  await drawer.getByText('用量看板').click()
  await expect(page).toHaveURL(/\/usage/)
  await ctx.close()
})
