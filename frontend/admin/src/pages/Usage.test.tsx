/**
 * T-09 用量页：满额/将满文案、CTA 不到注册、只读不能改套餐、网关失败不是套餐已满。
 * L1：Webhook / 套餐订购卡片。
 */
import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { FREE_TIER_FEATURE_COPY } from '@auto-agents/frontend-shared'

import { withQuery } from '../testUtils'
import Usage from './Usage'

jest.mock('../services/usage', () => ({
  fetchUsageOverview: jest.fn(),
  fetchUsageByMember: jest.fn().mockResolvedValue([]),
  fetchDeliveryWebhook: jest.fn().mockResolvedValue({ delivery_webhook_url: null }),
  putDeliveryWebhook: jest.fn(),
}))

jest.mock('../services/billing', () => ({
  CHANNEL_LABEL: { offline: '线下转账', alipay: '支付宝', wechat: '微信支付' },
  listPlans: jest.fn().mockResolvedValue([]),
  fetchSubscription: jest.fn().mockResolvedValue(null),
  listMyOrders: jest.fn().mockResolvedValue([]),
  createOrder: jest.fn(),
}))

jest.mock('../hooks/usePermission', () => ({
  usePermission: jest.fn(),
}))

jest.mock('../store/useAuthStore', () => ({
  useAuthStore: (sel: (s: { user: { tenant_role: string } | null }) => unknown) =>
    sel({ user: { tenant_role: 'viewer' } }),
}))

import { fetchUsageOverview } from '../services/usage'
import { usePermission } from '../hooks/usePermission'

const viewerPerm = {
  hasPermission: () => false,
  role: 'viewer',
  isAdmin: false,
  permissions: [],
  filteredMenus: [],
}

const adminPerm = {
  hasPermission: () => true,
  role: 'admin',
  isAdmin: true,
  permissions: [],
  filteredMenus: [],
}

const overview = (
  usage: { task_concurrency: number; result_storage: number; llm_tokens_month: number },
  // 将满/满额夹具用 100/100；GWT-01.1 免费档对照从 FREE_TIER_FEATURE_COPY 解析，禁止 mock(DEFAULT_QUOTA); expect(DEFAULT_QUOTA)
  quota = { task_concurrency: 5, result_storage: 100, llm_tokens_month: 100 },
) => ({
  tenant_id: 1,
  quota,
  usage,
  llm_by_provider: { 'provider:1': usage.llm_tokens_month },
  cost_by_provider: {},
  cost_cents_total: 0,
  timezone: 'Asia/Shanghai',
  year_month: '2026-09',
  alerts: [],
})

function renderUsage() {
  return render(
    <MemoryRouter>
      {withQuery(<Usage />)}
    </MemoryRouter>,
  )
}

function pageCopy(): string {
  return document.body.textContent || ''
}

beforeEach(() => {
  (usePermission as jest.Mock).mockReturnValue(viewerPerm)
  ;(fetchUsageOverview as jest.Mock).mockReset()
})

test('renders usage quota cards with webhook and billing', async () => {
  ;(fetchUsageOverview as jest.Mock).mockResolvedValueOnce(
    overview({ task_concurrency: 1, result_storage: 2, llm_tokens_month: 3 }),
  )
  renderUsage()
  expect(await screen.findByText('任务并发')).toBeInTheDocument()
  expect(await screen.findByText('任务交付 Webhook')).toBeInTheDocument()
  expect(await screen.findByText('套餐与订购')).toBeInTheDocument()
})

test('test_readonly_usage_no_plan_edit_gateway_failure_not_quota', async () => {
  ;(fetchUsageOverview as jest.Mock).mockResolvedValueOnce(
    overview({ task_concurrency: 1, result_storage: 10, llm_tokens_month: 50 }),
  )
  const { unmount } = renderUsage()
  expect(await screen.findByText('只读可见进度，不能改套餐')).toBeInTheDocument()
  expect(screen.getByText(/Asia\/Shanghai/)).toBeInTheDocument()
  expect(screen.queryByText('改套餐')).toBeNull()
  expect(screen.queryByRole('button', { name: '改套餐' })).toBeNull()
  expect(screen.queryByText('QUOTA_EXCEEDED')).toBeNull()
  expect(pageCopy()).not.toMatch(/\b429\b/)
  expect(pageCopy()).not.toContain('已达配额上限')
  unmount()

  ;(fetchUsageOverview as jest.Mock).mockRejectedValueOnce({
    response: {
      status: 503,
      data: { code: 'LLM_GATEWAY_UNREACHABLE', message: '平台 LLM 网关不可达' },
    },
  })
  renderUsage()
  expect(await screen.findByText('平台 LLM 网关不可达')).toBeInTheDocument()
  expect(screen.queryByText('已达配额上限')).toBeNull()
  expect(screen.queryByText('申请提升配额')).toBeNull()
  expect(screen.queryByText('QUOTA_EXCEEDED')).toBeNull()
  expect(pageCopy()).not.toMatch(/\b429\b/)
  expect(pageCopy()).not.toContain('/register')
})

test('near limit warning has no internal codes', async () => {
  ;(usePermission as jest.Mock).mockReturnValue(adminPerm)
  ;(fetchUsageOverview as jest.Mock).mockResolvedValueOnce(
    overview({ task_concurrency: 1, result_storage: 10, llm_tokens_month: 90 }),
  )
  renderUsage()
  expect(await screen.findByText('接近上限。超额操作会被拒绝。')).toBeInTheDocument()
  expect(screen.queryByText('QUOTA_EXCEEDED')).toBeNull()
  expect(pageCopy()).not.toMatch(/\b429\b/)
})

test('token full CTA does not go to register', async () => {
  ;(usePermission as jest.Mock).mockReturnValue(adminPerm)
  ;(fetchUsageOverview as jest.Mock).mockResolvedValueOnce(
    overview({ task_concurrency: 1, result_storage: 10, llm_tokens_month: 100 }),
  )
  renderUsage()
  expect(await screen.findByText('已达配额上限')).toBeInTheDocument()
  const cta = screen.getByRole('button', { name: '申请提升配额' })
  expect(cta.closest('a')).toBeNull()
  expect((cta as HTMLElement).getAttribute('href')).toBeNull()
  fireEvent.click(cta)
  const contact = await screen.findByRole('link', { name: /联系说明/ })
  expect(contact.getAttribute('href') || '').toMatch(/^mailto:/)
  expect(contact.getAttribute('href') || '').not.toContain('/register')
  expect(pageCopy()).not.toContain('/register')
  expect(pageCopy()).not.toContain('QUOTA_EXCEEDED')
})

test('platform admin without tenant sees enterprise-space copy not empty usage (GWT-16.3)', async () => {
  ;(usePermission as jest.Mock).mockReturnValue(adminPerm)
  ;(fetchUsageOverview as jest.Mock).mockResolvedValueOnce({
    scope: 'platform',
    message: '用量属于企业空间',
    timezone: 'Asia/Shanghai',
  })
  renderUsage()
  expect(await screen.findByText('用量属于企业空间')).toBeInTheDocument()
  expect(screen.queryByText('暂无用量数据')).toBeNull()
})

test('storage full CTA goes to results not register', async () => {
  ;(usePermission as jest.Mock).mockReturnValue(adminPerm)
  ;(fetchUsageOverview as jest.Mock).mockResolvedValueOnce(
    overview({ task_concurrency: 1, result_storage: 100, llm_tokens_month: 10 }),
  )
  renderUsage()
  expect(await screen.findByText('已达配额上限')).toBeInTheDocument()
  const go = screen.getByRole('link', { name: '去结果库' })
  expect(go).toHaveAttribute('href', '/data')
  expect(go).not.toHaveAttribute('href', '/register')
  expect(pageCopy()).not.toContain('/register')
})

/** GWT-01.1 Given 字面量。独立 oracle，不得从 DEFAULT_QUOTA 推导。 */
const GWT_01_1 = {
  concurrency: '5',
  storage: '10,000',
  tokensWan: '20 万',
  tokensFull: '200,000',
} as const

function leadingInt(phrase: string): number {
  const m = phrase.match(/^[\d,]+/)
  if (!m) throw new Error(`FREE_TIER_FEATURE_COPY missing leading number: ${phrase}`)
  return Number(m[0].replace(/,/g, ''))
}

/** Mock 用量上限取自定价免费档文案，不是 DEFAULT_QUOTA 往返。 */
function quotaFromPricingCopy() {
  const wan = FREE_TIER_FEATURE_COPY.llm_tokens_month.includes('万')
  return {
    task_concurrency: leadingInt(FREE_TIER_FEATURE_COPY.task_concurrency),
    result_storage: leadingInt(FREE_TIER_FEATURE_COPY.result_storage),
    llm_tokens_month: wan
      ? leadingInt(FREE_TIER_FEATURE_COPY.llm_tokens_month) * 10_000
      : leadingInt(FREE_TIER_FEATURE_COPY.llm_tokens_month),
  }
}

test('Usage page with Pricing FREE_TIER_FEATURE_COPY (5 / 10,000 / 20 万) shows the same three numbers as GWT-01.1', async () => {
  expect(FREE_TIER_FEATURE_COPY.task_concurrency).toBe(`${GWT_01_1.concurrency} 个并发任务`)
  expect(FREE_TIER_FEATURE_COPY.result_storage).toBe(`${GWT_01_1.storage} 条结果存储`)
  expect(FREE_TIER_FEATURE_COPY.llm_tokens_month).toBe(`${GWT_01_1.tokensWan} LLM tokens/月`)

  ;(usePermission as jest.Mock).mockReturnValue(adminPerm)
  ;(fetchUsageOverview as jest.Mock).mockResolvedValueOnce(
    overview(
      { task_concurrency: 0, result_storage: 0, llm_tokens_month: 0 },
      quotaFromPricingCopy(),
    ),
  )
  renderUsage()
  expect(await screen.findByText('任务并发')).toBeInTheDocument()
  const copy = pageCopy()
  expect(copy).toContain(`/ ${GWT_01_1.concurrency} 个运行中`)
  expect(copy).toContain(GWT_01_1.storage)
  expect(copy).toContain(GWT_01_1.tokensFull)
  expect(copy).not.toContain('预告')
})
