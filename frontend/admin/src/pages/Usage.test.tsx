/**
 * T-04 / FR-U02 用量页：将满≠已尽；申请提升分角色；存储满→去结果库。
 * GWT-50.3 我的订单 Tab 仍可读。GWT-50.13 专业档三数字与定价页同一套。
 * L1：Webhook / 套餐订购卡片。
 */
import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useSearchParams } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { FREE_TIER_FEATURE_COPY, PRO_TIER_FEATURE_COPY } from '@auto-agents/frontend-shared'

import Usage from './Usage'
import { useAuthStore } from '../store/useAuthStore'

jest.mock('../services/usage', () => ({
  fetchUsageOverview: jest.fn(),
  fetchUsageByMember: jest.fn().mockResolvedValue([]),
  fetchUpgradeIntent: jest.fn(),
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

jest.mock('antd', () => {
  const actual = jest.requireActual('antd')
  return {
    ...actual,
    message: {
      error: jest.fn(),
      success: jest.fn(),
      warning: jest.fn(),
      info: jest.fn(),
    },
  }
})

import { fetchUpgradeIntent, fetchUsageOverview } from '../services/usage'
import { createOrder, listMyOrders } from '../services/billing'
import { usePermission } from '../hooks/usePermission'
import {
  CHECKOUT_PATH_PRO,
  CONTACT_ADMIN_COPY,
  NEAR_LIMIT_COPY,
  PLAN_FULL_COPY,
  STORAGE_CTA,
  UPGRADE_CTA,
} from '../constants/collectCopy'

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

const operatorPerm = {
  hasPermission: () => true,
  role: 'operator',
  isAdmin: false,
  permissions: [],
  filteredMenus: [],
}

const userWith = (tenant_role: string) => ({
  access_token: 'test-token',
  token_type: 'bearer',
  username: 'alice',
  is_admin: false,
  tenant_id: 1,
  tenant_role,
})

const overview = (
  usage: { task_concurrency: number; result_storage: number; llm_tokens_month: number },
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

function CheckoutProbe() {
  const [params] = useSearchParams()
  return <div data-testid="checkout-probe">{params.get('product')}</div>
}

function renderUsage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter initialEntries={['/usage']}>
      <QueryClientProvider client={client}>
        <Routes>
          <Route path="/usage" element={<Usage />} />
          <Route path="/billing/checkout" element={<CheckoutProbe />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

function pageCopy(): string {
  return document.body.textContent || ''
}

function assertNoForbidden() {
  expect(pageCopy()).not.toContain('当前可买')
  expect(pageCopy()).not.toContain('QUOTA_EXCEEDED')
  expect(pageCopy()).not.toMatch(/\b429\b/)
  expect(pageCopy()).not.toContain('申请提升配额')
  expect(pageCopy()).not.toContain('/register')
}

beforeEach(() => {
  ;(usePermission as jest.Mock).mockReturnValue(viewerPerm)
  ;(fetchUsageOverview as jest.Mock).mockReset()
  useAuthStore.setState({ token: null, user: userWith('viewer'), isAuthenticated: false, rememberMe: false })
  ;(fetchUpgradeIntent as jest.Mock).mockReset().mockResolvedValue({
    action: 'contact_admin', product: 'plan_pro', checkout_path: null, message: CONTACT_ADMIN_COPY,
  })
  ;(createOrder as jest.Mock).mockReset()
  ;(listMyOrders as jest.Mock).mockReset().mockResolvedValue([])
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
  expect(screen.queryByRole('button', { name: UPGRADE_CTA })).toBeNull()
  expect(pageCopy()).not.toContain(PLAN_FULL_COPY)
  unmount()

  ;(fetchUsageOverview as jest.Mock).mockRejectedValueOnce({
    response: {
      status: 503,
      data: { code: 'LLM_GATEWAY_UNREACHABLE', message: '平台 LLM 网关不可达' },
    },
  })
  renderUsage()
  expect(await screen.findByText('平台 LLM 网关不可达')).toBeInTheDocument()
  expect(screen.queryByText(PLAN_FULL_COPY)).toBeNull()
  expect(screen.queryByText('申请提升配额')).toBeNull()
  assertNoForbidden()
})

test('GWT-U02.5 near limit warning has no full copy and no 申请提升', async () => {
  ;(usePermission as jest.Mock).mockReturnValue(adminPerm)
  ;(fetchUsageOverview as jest.Mock).mockResolvedValueOnce(
    overview({ task_concurrency: 1, result_storage: 10, llm_tokens_month: 90 }),
  )
  renderUsage()
  expect(await screen.findByText(NEAR_LIMIT_COPY)).toBeInTheDocument()
  expect(screen.queryByText(PLAN_FULL_COPY)).toBeNull()
  expect(screen.queryByRole('button', { name: UPGRADE_CTA })).toBeNull()
  assertNoForbidden()
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

test('GWT-U02.2 storage full CTA goes to results, no 申请提升', async () => {
  ;(usePermission as jest.Mock).mockReturnValue(adminPerm)
  useAuthStore.setState({ user: userWith('owner') })
  ;(fetchUsageOverview as jest.Mock).mockResolvedValueOnce(
    overview({ task_concurrency: 1, result_storage: 100, llm_tokens_month: 10 }),
  )
  renderUsage()
  expect(await screen.findByText(PLAN_FULL_COPY)).toBeInTheDocument()
  const go = screen.getByRole('link', { name: STORAGE_CTA })
  expect(go).toHaveAttribute('href', '/data')
  expect(screen.queryByRole('button', { name: UPGRADE_CTA })).toBeNull()
  assertNoForbidden()
})

test('GWT-U02.6 operator 申请提升 lands on contact-admin, no order no checkout', async () => {
  ;(usePermission as jest.Mock).mockReturnValue(operatorPerm)
  useAuthStore.setState({ user: userWith('operator') })
  ;(fetchUsageOverview as jest.Mock).mockResolvedValueOnce(
    overview({ task_concurrency: 1, result_storage: 10, llm_tokens_month: 100 }),
  )
  renderUsage()
  expect(await screen.findByText(PLAN_FULL_COPY)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: UPGRADE_CTA }))
  expect(await screen.findByText(CONTACT_ADMIN_COPY)).toBeInTheDocument()
  expect(screen.queryByTestId('checkout-probe')).toBeNull()
  expect(createOrder).not.toHaveBeenCalled()
  assertNoForbidden()
})

test('GWT-U02.6 viewer 申请提升 lands on contact-admin', async () => {
  useAuthStore.setState({ user: userWith('viewer') })
  ;(fetchUsageOverview as jest.Mock).mockResolvedValueOnce(
    overview({ task_concurrency: 1, result_storage: 10, llm_tokens_month: 100 }),
  )
  renderUsage()
  fireEvent.click(await screen.findByRole('button', { name: UPGRADE_CTA }))
  expect(await screen.findByText(CONTACT_ADMIN_COPY)).toBeInTheDocument()
  expect(createOrder).not.toHaveBeenCalled()
})

test('GWT-U02.7 buyer 申请提升 goes to /billing/checkout?product=plan_pro', async () => {
  ;(usePermission as jest.Mock).mockReturnValue(adminPerm)
  useAuthStore.setState({ user: userWith('owner') })
  ;(fetchUpgradeIntent as jest.Mock).mockResolvedValueOnce({
    action: 'checkout', product: 'plan_pro', checkout_path: CHECKOUT_PATH_PRO, message: '去结账',
  })
  ;(fetchUsageOverview as jest.Mock).mockResolvedValueOnce(
    overview({ task_concurrency: 1, result_storage: 10, llm_tokens_month: 100 }),
  )
  renderUsage()
  fireEvent.click(await screen.findByRole('button', { name: UPGRADE_CTA }))
  expect(await screen.findByTestId('checkout-probe')).toHaveTextContent('plan_pro')
  expect(createOrder).not.toHaveBeenCalled()
  await waitFor(() => expect(fetchUpgradeIntent).toHaveBeenCalled())
})

test('task concurrency full uses 已达配额上限 + 申请提升, not worker', async () => {
  ;(usePermission as jest.Mock).mockReturnValue(adminPerm)
  useAuthStore.setState({ user: userWith('owner') })
  ;(fetchUsageOverview as jest.Mock).mockResolvedValueOnce(
    overview({ task_concurrency: 5, result_storage: 10, llm_tokens_month: 50 }),
  )
  renderUsage()
  expect(await screen.findByText(PLAN_FULL_COPY)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: UPGRADE_CTA })).toBeInTheDocument()
  expect(pageCopy()).not.toContain('采集未运行，不会出数')
  assertNoForbidden()
})

test('GWT-50.3 readonly viewer can open 我的订单 tab (read surface)', async () => {
  ;(fetchUsageOverview as jest.Mock).mockResolvedValueOnce(
    overview({ task_concurrency: 1, result_storage: 10, llm_tokens_month: 50 }),
  )
  ;(listMyOrders as jest.Mock).mockResolvedValue([
    { id: 9, plan_id: 2, plan_name: '专业档', amount_cents: 29900, amount_yuan: 299, status: 'pending', channel: 'offline' },
  ])
  renderUsage()
  expect(await screen.findByText('只读可见进度，不能改套餐')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('tab', { name: '我的订单' }))
  expect(await screen.findByText('专业档', {}, { timeout: 15000 })).toBeInTheDocument()
  expect(screen.getByText(/299\s*元/)).toBeInTheDocument()
})

const GWT_01_1 = {
  concurrency: '5',
  storage: '10,000',
  tokensWan: '20 万',
  tokensFull: '200,000',
} as const

const GWT_50_13 = {
  concurrency: '50',
  storage: '200,000',
  tokensWan: '500 万',
  tokensFull: '5,000,000',
} as const

function leadingInt(phrase: string): number {
  const m = phrase.match(/^[\d,]+/)
  if (!m) throw new Error(`tier feature copy missing leading number: ${phrase}`)
  return Number(m[0].replace(/,/g, ''))
}

type TierFeatureCopy = { task_concurrency: string; result_storage: string; llm_tokens_month: string }

function quotaFromTierCopy(copy: TierFeatureCopy) {
  const wan = copy.llm_tokens_month.includes('万')
  return {
    task_concurrency: leadingInt(copy.task_concurrency),
    result_storage: leadingInt(copy.result_storage),
    llm_tokens_month: wan
      ? leadingInt(copy.llm_tokens_month) * 10_000
      : leadingInt(copy.llm_tokens_month),
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
      quotaFromTierCopy(FREE_TIER_FEATURE_COPY),
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

test('GWT-50.13 (QA-23) pro-tier fixture enforces the same three numbers as the pricing page', async () => {
  expect(PRO_TIER_FEATURE_COPY.task_concurrency).toBe(`${GWT_50_13.concurrency} 个并发任务`)
  expect(PRO_TIER_FEATURE_COPY.result_storage).toBe(`${GWT_50_13.storage} 条结果存储`)
  expect(PRO_TIER_FEATURE_COPY.llm_tokens_month).toBe(`${GWT_50_13.tokensWan} LLM tokens/月`)

  ;(usePermission as jest.Mock).mockReturnValue(adminPerm)
  ;(fetchUsageOverview as jest.Mock).mockResolvedValueOnce(
    overview(
      { task_concurrency: 12, result_storage: 30000, llm_tokens_month: 1200000 },
      quotaFromTierCopy(PRO_TIER_FEATURE_COPY),
    ),
  )
  renderUsage()
  expect(await screen.findByText('任务并发')).toBeInTheDocument()
  const copy = pageCopy()
  expect(copy).toContain(`/ ${GWT_50_13.concurrency} 个运行中`)
  expect(copy).toContain(GWT_50_13.storage)
  expect(copy).toContain(GWT_50_13.tokensFull)
  expect(copy).not.toContain('预告')
})
