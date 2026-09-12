/**
 * T-23 / FR-84（GWT-84.3/84.4）：超管待确认收款 + 产品事实 Tab 失败≠空。
 * - GWT-84.4：收款列表失败 = 「待确认收款列表加载失败。检查网络后重试。」+ 可点重试，
 *   不是默认「暂无数据」；重试真拉。
 * - 真 0（成功且 0 条 pending）= 「还没有待确认的收款。租户提交线下升级申请后会出现在这里。」
 *   （edge-states 钉句），不是失败句。
 * - GWT-84.3：租户直打 /platform-ops（收款与产品事实两查询面所在页）= 缺页同形 404，不是空表。
 * - 产品事实 Tab 失败/真 0 同走 FR-84 句族（不空表冒充无事件）。
 */
import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useAuthStore } from '../store/useAuthStore'
import App from '../App'
import PlatformOps from './PlatformOps'
import { listTenants } from '../services/platformOps'
import { listPendingOrders } from '../services/billing'
import { listProductEvents } from '../services/productEvents'

jest.mock('../services/platformOps', () => ({
  listTenants: jest.fn(),
  patchTenant: jest.fn(),
}))
jest.mock('../services/billing', () => ({
  listPendingOrders: jest.fn(),
  confirmOrder: jest.fn(),
}))
jest.mock('../services/productEvents', () => ({
  listProductEvents: jest.fn(),
}))
// App 级守卫用例：端点一律拒绝（守卫短路，不应发出任何页面请求）
jest.mock('../services/api', () => ({
  __esModule: true,
  default: {
    get: jest.fn(() => Promise.reject(new Error('mock network'))),
    post: jest.fn(() => Promise.reject(new Error('mock network'))),
    put: jest.fn(() => Promise.reject(new Error('mock network'))),
    patch: jest.fn(() => Promise.reject(new Error('mock network'))),
    delete: jest.fn(() => Promise.reject(new Error('mock network'))),
  },
  unwrap: jest.fn(),
}))

const orders = listPendingOrders as jest.Mock
const events = listProductEvents as jest.Mock

// 默认激活的「租户管理」Tab 给 1 行——避免其空表「暂无数据」留在 DOM 干扰跨 Tab 禁句断言
const TENANT_ROW = {
  id: 1, slug: 'acme', name: 'Acme 企业', status: 'active',
  quota: { task_concurrency: 2, result_storage: 100, llm_tokens_month: 1000 },
  expires_at: null,
}
const ORDER = { id: 41, plan_id: 2, amount_cents: 19900, status: 'pending', channel: 'offline' }

beforeEach(() => {
  useAuthStore.setState({ token: null, user: null, isAuthenticated: false, rememberMe: false })
  ;(listTenants as jest.Mock).mockReset().mockResolvedValue([TENANT_ROW])
  orders.mockReset()
  events.mockReset().mockResolvedValue({ total: 0, items: [], timezone: 'Asia/Shanghai' })
})

const renderOps = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <PlatformOps />
    </QueryClientProvider>,
  )
}

test('GWT-84.4 pending orders failure shows failure sentence + retry, not default 暂无数据', async () => {
  orders.mockRejectedValue(new Error('network down'))
  renderOps()
  fireEvent.click(screen.getByText('待确认收款'))
  expect(await screen.findByText('待确认收款列表加载失败。检查网络后重试。', {}, { timeout: 15000 })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /重\s*试/ })).toBeInTheDocument()
  // 失败不得画成默认空表句，也不得串成真 0 句
  expect(screen.queryByText(/暂无数据/)).not.toBeInTheDocument()
  expect(screen.queryByText(/还没有待确认的收款/)).not.toBeInTheDocument()
})

test('GWT-84.4 retry refetches the pending orders list', async () => {
  orders.mockRejectedValueOnce(new Error('network down')).mockResolvedValueOnce([ORDER])
  renderOps()
  fireEvent.click(screen.getByText('待确认收款'))
  expect(await screen.findByText('待确认收款列表加载失败。检查网络后重试。', {}, { timeout: 15000 })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /重\s*试/ }))
  expect(await screen.findByText('41', {}, { timeout: 15000 })).toBeInTheDocument()
  expect(screen.queryByText(/加载失败/)).not.toBeInTheDocument()
})

test('pending orders true zero (200 + 0 pending) shows 还没有待确认的收款 sentence, not failure', async () => {
  orders.mockResolvedValue([])
  renderOps()
  fireEvent.click(screen.getByText('待确认收款'))
  // waitFor+getByText：antd Table 空态节点在 loading 翻转时会换节点，findByText 单点断言可能拿到已换下的节点
  await waitFor(() => {
    expect(screen.getByText('还没有待确认的收款。租户提交线下升级申请后会出现在这里。')).toBeInTheDocument()
  }, { timeout: 15000 })
  expect(screen.queryByText(/加载失败/)).not.toBeInTheDocument()
  expect(screen.queryByText(/暂无数据/)).not.toBeInTheDocument()
})

test('product-events tab failure shows FR-84 sentence + retry, not empty-table masquerade', async () => {
  events.mockRejectedValue(new Error('network down'))
  renderOps()
  fireEvent.click(screen.getByText('产品事实'))
  expect(await screen.findByText('产品事实加载失败。检查网络后重试。', {}, { timeout: 15000 })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /重\s*试/ })).toBeInTheDocument()
  expect(screen.queryByText(/还没有产品事实/)).not.toBeInTheDocument()
  expect(screen.queryByText(/暂无数据/)).not.toBeInTheDocument()
})

test('product-events tab true zero shows 还没有产品事实 sentence, not failure', async () => {
  renderOps()
  fireEvent.click(screen.getByText('产品事实'))
  expect(await screen.findByText('还没有产品事实。访客浏览或租户完成动作后会出现在这里。', {}, { timeout: 15000 })).toBeInTheDocument()
  expect(screen.queryByText(/加载失败/)).not.toBeInTheDocument()
})

test('GWT-84.3 tenant direct hit on /platform-ops is 404 shell for both pending-orders & product-events surfaces', async () => {
  useAuthStore.setState({
    token: 't', isAuthenticated: true, rememberMe: false,
    user: {
      access_token: 't', token_type: 'bearer', username: 'boss',
      is_admin: true, role: 'admin', is_platform_admin: false, tenant_id: 3,
    },
  })
  window.history.replaceState({}, '', '/platform-ops')
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  )

  // 与「页面不存在」同形（MainLayout 平台写面守卫，T-15/T-29 已落）
  expect(await screen.findByText('页面不存在或已被移除')).toBeInTheDocument()
  // 收款与产品事实两查询面（本页两 Tab）都不出现——不是空表
  expect(screen.queryByText('待确认收款')).not.toBeInTheDocument()
  expect(screen.queryByText('产品事实')).not.toBeInTheDocument()
  expect(screen.queryByText('在线支付未开通。确认收款后把企业套餐配额改到该订单档。')).not.toBeInTheDocument()
  expect(screen.queryByPlaceholderText('如 market_subscribe_succeeded')).not.toBeInTheDocument()
  expect(screen.queryByText(/暂无数据/)).not.toBeInTheDocument()
})
