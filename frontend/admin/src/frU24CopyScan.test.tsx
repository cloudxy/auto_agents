/**
 * T-23 / FR-U24 机械钉：租户可见面源码与渲染不得出现 FR-U24 四字。
 * 不实现支付通知。结账保持通道未开通空态。
 */
import fs from 'fs'
import path from 'path'
import React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

jest.mock('./services/billing', () => ({
  previewCheckout: jest.fn(),
  createOrder: jest.fn(),
  createCheckout: jest.fn(),
  listMyOrders: jest.fn(),
}))

jest.mock('./services/relay', () => ({
  fetchRelayPage: jest.fn(),
  fetchRelaySku: jest.fn(),
  createRelayGroup: jest.fn(),
  patchRelayGroup: jest.fn(),
  issueRelayToken: jest.fn(),
  revokeRelayToken: jest.fn(),
}))

jest.mock('./services/capabilities', () => ({
  listPublicAssets: jest.fn(),
}))

// zustand 的 hook 两种调用形态都合法：带 selector 取片段，或不带参数取整个 store。
// TenantShelf（T-08）经 usePermission 走的是**不带 selector** 的 `useAuthStore()`，
// 故 mock 必须两种都支持，否则渲染即 `sel is not a function`。
jest.mock('./store/useAuthStore', () => {
  const state = {
    user: { tenant_id: 1, tenant_role: 'owner', is_platform_admin: false },
    isAuthenticated: true,
  }
  return {
    useAuthStore: (sel?: (s: typeof state) => unknown) =>
      (typeof sel === 'function' ? sel(state) : state),
  }
})

import { previewCheckout, listMyOrders } from './services/billing'
import { fetchRelayPage, fetchRelaySku } from './services/relay'
import { listPublicAssets } from './services/capabilities'
import Checkout from './pages/Checkout'
import RelayGroups from './pages/RelayGroups'
import TenantShelf from './pages/market/TenantShelf'

const NEEDLES = ['当前可买', '支付已通'] as const
const SRC_ROOT = __dirname
const SURFACES = [
  'pages/Checkout.tsx',
  'pages/RelayGroups.tsx',
  'pages/Capabilities.tsx',
  'pages/market/TenantShelf.tsx',
  'pages/Usage.tsx',
  'pages/Pricing.tsx',
  'config/menuConfig.tsx',
] as const

function skipName(name: string): boolean {
  if (name === 'node_modules' || name === '__mocks__' || name === 'dist') return true
  return /\.(test|spec)\.[jt]sx?$/.test(name)
}

function walkTs(dir: string): string[] {
  const out: string[] = []
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    if (skipName(ent.name)) continue
    const full = path.join(dir, ent.name)
    if (ent.isDirectory()) {
      out.push(...walkTs(full))
      continue
    }
    if (/\.[jt]sx?$/.test(ent.name) && !ent.name.endsWith('.d.ts')) out.push(full)
  }
  return out
}

function filesWithNeedle(root: string, needle: string): string[] {
  return walkTs(root).filter((file) => fs.readFileSync(file, 'utf8').includes(needle))
}

function wrap(ui: React.ReactElement, url: string, route: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path={route} element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  ;(previewCheckout as jest.Mock).mockReset()
  ;(fetchRelayPage as jest.Mock).mockReset()
  ;(fetchRelaySku as jest.Mock).mockReset()
  ;(listMyOrders as jest.Mock).mockReset()
  ;(listPublicAssets as jest.Mock).mockReset()
  ;(previewCheckout as jest.Mock).mockResolvedValue({
    product: 'plan_pro',
    channels: [],
    empty_state: null,
    can_pay: false,
    order_id: null,
    amount_cents: 29900,
  })
  ;(fetchRelaySku as jest.Mock).mockResolvedValue({
    status: 'none', can_issue: false, empty_title: '未开通中转',
    empty_hint: '开通后才能查看本企业用量并签发令牌。',
    upgrade: { action: 'checkout', product: 'relay', checkout_path: '/billing/checkout?product=relay', message: '去升级' },
  })
  ;(listMyOrders as jest.Mock).mockResolvedValue([])
  ;(fetchRelayPage as jest.Mock).mockResolvedValue({
    groups: [],
    tokens: [],
    groupsMessage: '操作成功',
    tokensMessage: '还没有令牌',
  })
  ;(listPublicAssets as jest.Mock).mockResolvedValue({
    items: [], total: 0, market_closed: false, message: '暂无已上架能力',
  })
})

test('GWT-M50/M15 mechanical nail: tenant surfaces have no 当前可买 or 支付已通', async () => {
  NEEDLES.forEach((needle) => expect(filesWithNeedle(SRC_ROOT, needle)).toEqual([]))
  SURFACES.forEach((rel) => {
    const full = path.join(SRC_ROOT, rel)
    expect(fs.existsSync(full)).toBe(true)
    const src = fs.readFileSync(full, 'utf8')
    NEEDLES.forEach((needle) => expect(src).not.toContain(needle))
    expect(src).not.toMatch(/编辑定价|改定价文案/)
  })
  const checkoutSrc = fs.readFileSync(path.join(SRC_ROOT, 'pages/Checkout.tsx'), 'utf8')
  expect(checkoutSrc).not.toMatch(/payment_succeeded|\/billing\/notify/)

  wrap(<Checkout />, '/billing/checkout?product=plan_pro', '/billing/checkout')
  expect(await screen.findByRole('button', { name: '提交开通' })).toBeInTheDocument()
  NEEDLES.forEach((needle) => expect(document.body.textContent || '').not.toContain(needle))
  cleanup()

  wrap(<RelayGroups />, '/relay', '/relay')
  expect(await screen.findByText('未开通中转')).toBeInTheDocument()
  NEEDLES.forEach((needle) => expect(document.body.textContent || '').not.toContain(needle))
  cleanup()

  wrap(
    <TenantShelf canSubscribe onSubscribe={() => undefined} />,
    '/capabilities',
    '/capabilities',
  )
  expect(await screen.findByText('暂无已上架能力')).toBeInTheDocument()
  NEEDLES.forEach((needle) => expect(document.body.textContent || '').not.toContain(needle))
})
