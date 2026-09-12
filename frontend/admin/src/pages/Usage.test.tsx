/**
 * T-09 用量页：满额/将满文案、CTA 不到注册、只读不能改套餐、网关失败不是套餐已满。
 * T-03（FR-50 UI 面）：
 * - GWT-50.12：满额动词统一骨架「提交升级申请」，不出现购买形「提交升级订单」。
 * - GWT-50.1/50.6：存储满→去结果库；token/并发满→同一「提交升级申请」入口（channel=offline）；
 *   不到 /register；经办/只读无申请按钮 +「请联系企业管理员」（映射 T-01 code，无内码）。
 * - GWT-50.3：页内「我的订单」Tab（listMyOrders 渲染；只读也能看）。
 * - GWT-50.13（QA-23）：专业档三数字与定价页同一套（PRO_TIER_FEATURE_COPY 单源）。
 */
import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { FREE_TIER_FEATURE_COPY, PRO_TIER_FEATURE_COPY } from '@auto-agents/frontend-shared'

import Usage from './Usage'
import { useAuthStore } from '../store/useAuthStore'

jest.mock('../services/usage', () => ({
  fetchUsageOverview: jest.fn(),
  fetchUsageByMember: jest.fn().mockResolvedValue([]),
}))

jest.mock('../services/billing', () => ({
  listPlans: jest.fn().mockResolvedValue([{ id: 2, slug: 'pro', name: '专业档', price_cents: 29900, period: 'month' }]),
  createOrder: jest.fn().mockResolvedValue({ id: 9, plan_id: 2, plan_name: '专业档', amount_cents: 29900, amount_yuan: 299, status: 'pending', channel: 'offline' }),
  listMyOrders: jest.fn().mockResolvedValue([]),
}))

jest.mock('../hooks/usePermission', () => ({
  usePermission: jest.fn(),
}))

// antd 6 toast 不进 testing-library 容器；钉 message.* 映射文案（Members.test 同款）
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

import { message } from 'antd'
import { fetchUsageOverview } from '../services/usage'
import { createOrder, listMyOrders, listPlans } from '../services/billing'
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
  // 将满/满额夹具用 100/100；GWT-01.1 免费档对照从 FREE_TIER_FEATURE_COPY 解析，禁止 mock(DEFAULT_QUOTA); expect(DEFAULT_QUOTA)
  quota = { task_concurrency: 5, result_storage: 100, llm_tokens_month: 100 },
) => ({
  tenant_id: 1,
  quota,
  usage,
  llm_by_provider: { 'provider:1': usage.llm_tokens_month },
  timezone: 'Asia/Shanghai',
  year_month: '2026-09',
  alerts: [],
})

function renderUsage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <Usage />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

function pageCopy(): string {
  return document.body.textContent || ''
}

beforeEach(() => {
  ;(usePermission as jest.Mock).mockReturnValue(viewerPerm)
  ;(fetchUsageOverview as jest.Mock).mockReset()
  useAuthStore.setState({ token: null, user: userWith('viewer'), isAuthenticated: false, rememberMe: false })
  ;(createOrder as jest.Mock).mockReset().mockResolvedValue({ id: 9, plan_id: 2, plan_name: '专业档', amount_cents: 29900, amount_yuan: 299, status: 'pending', channel: 'offline' })
  ;(listPlans as jest.Mock).mockReset().mockResolvedValue([{ id: 2, slug: 'pro', name: '专业档', price_cents: 29900, period: 'month' }])
  ;(listMyOrders as jest.Mock).mockReset().mockResolvedValue([])
  ;(message.error as jest.Mock).mockClear()
  ;(message.success as jest.Mock).mockClear()
  ;(message.warning as jest.Mock).mockClear()
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
  // 未满额：无申请按钮，也无「请联系企业管理员」旁注
  expect(screen.queryByRole('button', { name: '提交升级申请' })).toBeNull()
  expect(screen.queryByText('请联系企业管理员')).toBeNull()
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

test('storage full CTA goes to results not register (GWT-50.1)', async () => {
  ;(usePermission as jest.Mock).mockReturnValue(adminPerm)
  useAuthStore.setState({ user: userWith('owner') })
  ;(fetchUsageOverview as jest.Mock).mockResolvedValueOnce(
    overview({ task_concurrency: 1, result_storage: 100, llm_tokens_month: 10 }),
  )
  renderUsage()
  expect(await screen.findByText('已达配额上限')).toBeInTheDocument()
  const go = screen.getByRole('link', { name: '去结果库' })
  expect(go).toHaveAttribute('href', '/data')
  expect(go).not.toHaveAttribute('href', '/register')
  expect(pageCopy()).not.toContain('/register')
  // 存储满：只有去结果库，不出现申请入口（edge-states 边界表）
  expect(screen.queryByRole('button', { name: '提交升级申请' })).toBeNull()
  // 不出现「没有下一步 / 尚未开通」否定线下申请骨架（GWT-50.1）
  expect(pageCopy()).not.toMatch(/没有下一步|尚未开通/)
})

test('GWT-50.12 token full (owner) shows skeleton verb 提交升级申请, never purchase form', async () => {
  ;(usePermission as jest.Mock).mockReturnValue(adminPerm)
  useAuthStore.setState({ user: userWith('owner') })
  ;(fetchUsageOverview as jest.Mock).mockResolvedValueOnce(
    overview({ task_concurrency: 1, result_storage: 10, llm_tokens_month: 100 }),
  )
  renderUsage()
  expect(await screen.findByText('已达配额上限')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '提交升级申请' })).toBeInTheDocument()
  expect(screen.queryByText('提交升级订单')).toBeNull()
  expect(pageCopy()).not.toContain('/register')
  expect(pageCopy()).not.toMatch(/QUOTA_EXCEEDED|FORBIDDEN|\b429\b/)
  // 「本波不提供自助改套餐或支付」说明与申请入口同屏并存（GWT-50.12 后半）
  fireEvent.click(screen.getByRole('button', { name: '申请提升配额' }))
  expect(await screen.findByText(/本波不提供自助改套餐或支付/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '提交升级申请' })).toBeInTheDocument()
})

test('GWT-50.6 task concurrency full shows 已达任务并发上限 with same offline entry', async () => {
  ;(usePermission as jest.Mock).mockReturnValue(adminPerm)
  useAuthStore.setState({ user: userWith('owner') })
  ;(fetchUsageOverview as jest.Mock).mockResolvedValueOnce(
    overview({ task_concurrency: 5, result_storage: 10, llm_tokens_month: 50 }),
  )
  renderUsage()
  expect(await screen.findByText('已达任务并发上限')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '提交升级申请' })).toBeInTheDocument()
  expect(pageCopy()).not.toContain('/register')
})

test('GWT-50.7 operator full sees contact-admin note, no apply button, no internal codes', async () => {
  ;(usePermission as jest.Mock).mockReturnValue(adminPerm)
  useAuthStore.setState({ user: userWith('operator') })
  ;(fetchUsageOverview as jest.Mock).mockResolvedValueOnce(
    overview({ task_concurrency: 1, result_storage: 10, llm_tokens_month: 100 }),
  )
  renderUsage()
  expect(await screen.findByText('已达配额上限')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '提交升级申请' })).toBeNull()
  expect(screen.getByText('请联系企业管理员')).toBeInTheDocument()
  expect(pageCopy()).not.toMatch(/QUOTA_EXCEEDED|FORBIDDEN|\b429\b/)
})

test('owner submits offline upgrade order and gets pinned toast + 去我的订单 (GWT-50.2)', async () => {
  ;(usePermission as jest.Mock).mockReturnValue(adminPerm)
  useAuthStore.setState({ user: userWith('owner') })
  ;(fetchUsageOverview as jest.Mock).mockResolvedValueOnce(
    overview({ task_concurrency: 1, result_storage: 10, llm_tokens_month: 100 }),
  )
  ;(listMyOrders as jest.Mock).mockResolvedValueOnce([
    { id: 9, plan_id: 2, plan_name: '专业档', amount_cents: 29900, amount_yuan: 299, status: 'pending', channel: 'offline' },
  ])
  renderUsage()
  fireEvent.click(await screen.findByRole('button', { name: '提交升级申请' }))
  await waitFor(() => expect(createOrder).toHaveBeenCalledWith(2))
  expect(message.success).toHaveBeenCalledWith(
    expect.stringMatching(/已提交升级申请，等待管理员确认收款/),
  )
  // 次链「去我的订单」：页内 Tab 入口
  fireEvent.click(screen.getByRole('button', { name: '去我的订单' }))
  expect((await screen.findAllByText('专业档', {}, { timeout: 15000 })).length).toBeGreaterThanOrEqual(1)
  expect(screen.getByText('待确认收款')).toBeInTheDocument()
})

test('ORDER_PENDING_EXISTS maps to pinned copy + 去我的订单, no code literal (GWT-50.15)', async () => {
  ;(usePermission as jest.Mock).mockReturnValue(adminPerm)
  useAuthStore.setState({ user: userWith('owner') })
  ;(fetchUsageOverview as jest.Mock).mockResolvedValueOnce(
    overview({ task_concurrency: 1, result_storage: 10, llm_tokens_month: 100 }),
  )
  ;(createOrder as jest.Mock).mockRejectedValueOnce({
    response: { status: 400, data: { success: false, code: 'ORDER_PENDING_EXISTS', message: '已有待确认的升级申请', data: null } },
  })
  renderUsage()
  fireEvent.click(await screen.findByRole('button', { name: '提交升级申请' }))
  await waitFor(() => expect(message.warning).toHaveBeenCalledWith('已有待确认的升级申请'))
  expect(screen.getByRole('button', { name: '去我的订单' })).toBeInTheDocument()
  expect(pageCopy()).not.toContain('ORDER_PENDING_EXISTS')
})

test('ORDER_ROLE_NOT_ALLOWED (backend T-01 code) maps to contact-admin, no FORBIDDEN literal', async () => {
  ;(usePermission as jest.Mock).mockReturnValue(adminPerm)
  useAuthStore.setState({ user: userWith('owner') })
  ;(fetchUsageOverview as jest.Mock).mockResolvedValueOnce(
    overview({ task_concurrency: 1, result_storage: 10, llm_tokens_month: 100 }),
  )
  ;(createOrder as jest.Mock).mockRejectedValueOnce({
    response: { status: 400, data: { success: false, code: 'ORDER_ROLE_NOT_ALLOWED', message: '请联系企业管理员', data: null } },
  })
  renderUsage()
  fireEvent.click(await screen.findByRole('button', { name: '提交升级申请' }))
  await waitFor(() => expect(message.error).toHaveBeenCalledWith(expect.stringMatching(/请联系企业管理员/)))
  expect(pageCopy()).not.toMatch(/ORDER_ROLE_NOT_ALLOWED|FORBIDDEN/)
})

test('GWT-50.3 readonly viewer can open 我的订单 tab (read surface)', async () => {
  ;(fetchUsageOverview as jest.Mock).mockResolvedValueOnce(
    overview({ task_concurrency: 1, result_storage: 10, llm_tokens_month: 50 }),
  )
  ;(listMyOrders as jest.Mock).mockResolvedValueOnce([
    { id: 9, plan_id: 2, plan_name: '专业档', amount_cents: 29900, amount_yuan: 299, status: 'pending', channel: 'offline' },
  ])
  renderUsage()
  expect(await screen.findByText('只读可见进度，不能改套餐')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('tab', { name: '我的订单' }))
  expect(await screen.findByText('专业档', {}, { timeout: 15000 })).toBeInTheDocument()
  expect(screen.getByText(/299\s*元/)).toBeInTheDocument()
})

/** GWT-01.1 Given 字面量。独立 oracle，不得从 DEFAULT_QUOTA 推导。 */
const GWT_01_1 = {
  concurrency: '5',
  storage: '10,000',
  tokensWan: '20 万',
  tokensFull: '200,000',
} as const

/** GWT-50.13（QA-23）Given 字面量：定价页专业档三条。独立 oracle，不得从 PRO_TIER_QUOTA 推导。 */
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

/** Mock 用量上限取自定价文案（免费档=FREE_TIER_FEATURE_COPY，专业档=PRO_TIER_FEATURE_COPY），不是常量往返。 */
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
  // 定价页（官网冻结字面）与用量页共用一套专业档三数字：PRO_TIER_FEATURE_COPY 钉住两边
  expect(PRO_TIER_FEATURE_COPY.task_concurrency).toBe(`${GWT_50_13.concurrency} 个并发任务`)
  expect(PRO_TIER_FEATURE_COPY.result_storage).toBe(`${GWT_50_13.storage} 条结果存储`)
  expect(PRO_TIER_FEATURE_COPY.llm_tokens_month).toBe(`${GWT_50_13.tokensWan} LLM tokens/月`)

  ;(usePermission as jest.Mock).mockReturnValue(adminPerm)
  // Given：该企业已按专业档执法（QA-23 夹具——不是本波确认履约）
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
