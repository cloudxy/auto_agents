/**
 * T-20 我的渠道组：SKU none/active/expired + T-10 签发一次明文。
 * 读 T-18 /relay/sku。租户不得当值班页。禁 FR-U24 四字。
 */
import React from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes, useSearchParams } from 'react-router-dom'

import RelayGroups from './RelayGroups'

jest.mock('../services/relay', () => ({
  fetchRelayPage: jest.fn(),
  fetchRelaySku: jest.fn(),
  createRelayGroup: jest.fn(),
  patchRelayGroup: jest.fn(),
  issueRelayToken: jest.fn(),
  revokeRelayToken: jest.fn(),
}))

jest.mock('../services/billing', () => ({
  listMyOrders: jest.fn(),
}))

// babel-jest 工厂引用 mock* 前缀变量（render 时才读取，无 TDZ）
const mockUserState: { current: Record<string, unknown> | null } = {
  current: null,
}

jest.mock('../store/useAuthStore', () => ({
  useAuthStore: (sel: (s: { user: Record<string, unknown> | null }) => unknown) =>
    sel({ user: mockUserState.current }),
}))

import { fetchRelayPage, fetchRelaySku, issueRelayToken } from '../services/relay'
import { listMyOrders } from '../services/billing'
import { CONTACT_ADMIN_COPY } from '../constants/collectCopy'

const OWNER = { tenant_id: 1, tenant_role: 'owner', is_platform_admin: false }
const OPERATOR = { tenant_id: 1, tenant_role: 'operator', is_platform_admin: false }
const VIEWER = { tenant_id: 1, tenant_role: 'viewer', is_platform_admin: false }

const TOKEN = {
  id: 11, group_id: 1, name: 'prod', key_prefix: 'sk-AbCd', quota_tokens: -1,
  used_tokens: 1200, status: 'active',
}
const GROUP = { id: 1, name: 'default', rpm_limit: 0, tpm_limit: 0, models: [], status: 'enabled' }
const PAGE_WITH_TOKEN = {
  groups: [GROUP],
  tokens: [TOKEN],
  groupsMessage: '操作成功',
  tokensMessage: '操作成功',
}
const EMPTY_PAGE = {
  groups: [],
  tokens: [],
  groupsMessage: '操作成功',
  tokensMessage: '还没有令牌',
}

const SKU_ACTIVE = {
  status: 'active', can_issue: true, empty_title: '', empty_hint: '', upgrade: null,
}
const SKU_NONE = {
  status: 'none', can_issue: false, empty_title: '未开通中转',
  empty_hint: '开通后才能查看本企业用量并签发令牌。',
  upgrade: {
    action: 'checkout', product: 'relay',
    checkout_path: '/billing/checkout?product=relay', message: '去升级',
  },
}
const SKU_EXPIRED = {
  status: 'expired', can_issue: false, empty_title: '中转已到期',
  empty_hint: '到期后不能签发新令牌，已签发的令牌也不能再用。',
  upgrade: {
    action: 'checkout', product: 'relay',
    checkout_path: '/billing/checkout?product=relay', message: '去升级',
  },
}
const SKU_NONE_OPERATOR = {
  ...SKU_NONE,
  upgrade: {
    action: 'contact_admin', product: 'relay', checkout_path: null, message: CONTACT_ADMIN_COPY,
  },
}

function CheckoutProbe() {
  const [params] = useSearchParams()
  return <div data-testid="checkout-probe">{params.get('product')}</div>
}
const OPERATOR_PAGE = {
  ...PAGE_WITH_TOKEN,
  groupsMessage: '当前账号不能签发，请联系企业管理员',
}
const ISSUE_BUTTON = /签\s*发\s*令\s*牌/
const MODAL_OK_ISSUE = /^签\s*发$/

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/relay']}>
        <Routes>
          <Route path="/relay" element={<RelayGroups />} />
          <Route path="/billing/checkout" element={<CheckoutProbe />} />
          <Route path="/register" element={<div>register-probe</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

async function issueFlow() {
  const buttons = await screen.findAllByRole('button', { name: ISSUE_BUTTON })
  fireEvent.click(buttons[0])
  fireEvent.change(screen.getByLabelText('备注名'), { target: { value: 'prod' } })
  fireEvent.click(screen.getByRole('button', { name: MODAL_OK_ISSUE }))
}

beforeEach(() => {
  jest.clearAllMocks()
  mockUserState.current = OWNER
  ;(fetchRelaySku as jest.Mock).mockResolvedValue(SKU_ACTIVE)
  ;(listMyOrders as jest.Mock).mockResolvedValue([])
  Object.defineProperty(window.navigator, 'onLine', {
    configurable: true,
    get: () => true,
  })
})

test('shows tenant groups copy and not platform channel controls', async () => {
  ;(fetchRelayPage as jest.Mock).mockResolvedValue(PAGE_WITH_TOKEN)
  renderPage()
  expect(await screen.findByText('default')).toBeInTheDocument()
  expect(screen.getByText(/本页只管理本企业令牌/)).toBeInTheDocument()
  expect(screen.queryByText('我的中转令牌')).not.toBeInTheDocument()
  expect(screen.queryByText('直连平台网关')).not.toBeInTheDocument()
})

test('gwt_60_1: issue shows plaintext once with base url and three steps on same screen', async () => {
  ;(fetchRelayPage as jest.Mock).mockResolvedValue({ ...PAGE_WITH_TOKEN, tokens: [] })
  ;(issueRelayToken as jest.Mock).mockResolvedValue({ ...TOKEN, plaintext_key: 'sk-RelaySecret123' })
  renderPage()
  await issueFlow()
  expect(await screen.findByText('请立即复制渠道组令牌')).toBeInTheDocument()
  expect(await screen.findByTestId('issued-plaintext')).toHaveTextContent('sk-RelaySecret123')
  // 同一屏：Base URL + 三步用法（页脚用法卡与弹窗内各一份，取弹窗内那份）
  const usageInModal = screen.getAllByTestId('relay-usage')
    .find((node) => node.closest('.ant-modal'))
  expect(usageInModal).toBeDefined()
  expect(usageInModal).toHaveTextContent('http://127.0.0.1:4000')
  expect(usageInModal).toHaveTextContent('复制 Base URL → 粘贴令牌 → 发一条请求')
  // 不得把出站拉数地址写成 Base URL；不出现平台网关钥匙
  expect(usageInModal?.textContent || '').not.toContain('/api/v1')
  expect(document.body.textContent || '').not.toContain('master')
})

test('gwt_60_11: after closing plaintext modal only prefix and status remain', async () => {
  ;(fetchRelayPage as jest.Mock)
    .mockResolvedValueOnce({ ...PAGE_WITH_TOKEN, tokens: [] })
    .mockResolvedValue(PAGE_WITH_TOKEN) // 再进页：列表无明文，只有前缀+状态
  ;(issueRelayToken as jest.Mock).mockResolvedValue({ ...TOKEN, plaintext_key: 'sk-RelaySecret123' })
  renderPage()
  await issueFlow()
  await screen.findByTestId('issued-plaintext')
  fireEvent.click(screen.getByRole('button', { name: /我已保存/ }))
  expect(await screen.findByText(/sk-AbCd/)).toBeInTheDocument()
  // 明文随弹窗消失（含关闭动画），列表只剩前缀+状态
  await waitFor(() => {
    expect(screen.queryByText(/sk-RelaySecret123/)).not.toBeInTheDocument()
  })
  // toast 句与行状态同文案「已签发」；钉令牌表，避免无动画时 toast 未卸导致 getByText 多匹配
  const tokenTable = screen.getAllByRole('table').find((t) => within(t).queryByText(/sk-AbCd/))
  expect(tokenTable).toBeTruthy()
  expect(within(tokenTable as HTMLElement).getByText('已签发')).toBeInTheDocument()
})

test('gwt_60_2: viewer sees usage number and cannot-issue note', async () => {
  ;(fetchRelayPage as jest.Mock).mockResolvedValue(OPERATOR_PAGE)
  mockUserState.current = VIEWER
  renderPage()
  expect(await screen.findByText('1,200')).toBeInTheDocument()
  expect(screen.getByText('当前账号不能签发，请联系企业管理员')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: ISSUE_BUTTON })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /新\s*建\s*渠\s*道\s*组/ })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '吊销' })).not.toBeInTheDocument()
})

test('gwt_60_4 / GWT-M23.3: opened SKU zero tokens is 还没有令牌 + issue, no third empty', async () => {
  ;(fetchRelayPage as jest.Mock).mockResolvedValue(EMPTY_PAGE)
  renderPage()
  expect(await screen.findByText('还没有令牌')).toBeInTheDocument()
  expect(screen.queryByText('还没有渠道组。创建后才能签发令牌。')).not.toBeInTheDocument()
  expect(screen.queryByText('未开通中转')).not.toBeInTheDocument()
  expect(screen.getByTestId('relay-usage')).toBeInTheDocument()
  expect(screen.queryByText('暂无数据')).not.toBeInTheDocument()
  expect(screen.getAllByRole('button', { name: ISSUE_BUTTON }).length).toBeGreaterThan(0)
})

test('gwt_60_7: operator sees usage/base url without write controls, not an empty table', async () => {
  ;(fetchRelayPage as jest.Mock).mockResolvedValue(OPERATOR_PAGE)
  mockUserState.current = OPERATOR
  renderPage()
  expect(await screen.findByText('prod')).toBeInTheDocument()
  expect(screen.getByText('当前账号不能签发，请联系企业管理员')).toBeInTheDocument()
  expect(screen.getByTestId('relay-usage')).toHaveTextContent('复制 Base URL')
  expect(screen.getByText('1,200')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: ISSUE_BUTTON })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '吊销' })).not.toBeInTheDocument()
})

test('gwt_84_1: load failure shows retry sentence, not an empty table', async () => {
  ;(fetchRelayPage as jest.Mock).mockRejectedValue(new Error('network down'))
  renderPage()
  expect(await screen.findByText('渠道组加载失败。检查网络后重试。')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /重\s*试/ })).toBeInTheDocument()
  expect(screen.queryByText('暂无数据')).not.toBeInTheDocument()
  expect(screen.queryByText('还没有令牌')).not.toBeInTheDocument()
})

test('issue failure stays visible inline and modal stays open, no fake success', async () => {
  ;(fetchRelayPage as jest.Mock).mockResolvedValue({ ...PAGE_WITH_TOKEN, tokens: [] })
  ;(issueRelayToken as jest.Mock).mockRejectedValue({
    response: { data: { code: 'RELAY_GATEWAY_UNAVAILABLE', message: '平台网关暂时不可用，令牌签发失败，请稍后重试。' } },
  })
  renderPage()
  await issueFlow()
  expect(await screen.findByText('平台网关暂时不可用，令牌签发失败，请稍后重试。')).toBeInTheDocument()
  // 弹窗不关（标题仍在）、无明文、无假成功
  expect(document.querySelector('.ant-modal-title')?.textContent).toContain('签发令牌')
  expect(screen.queryByTestId('issued-plaintext')).not.toBeInTheDocument()
})

test('issue offline shows offline sentence and no plaintext', async () => {
  ;(fetchRelayPage as jest.Mock).mockResolvedValue({ ...PAGE_WITH_TOKEN, tokens: [] })
  Object.defineProperty(window.navigator, 'onLine', { configurable: true, get: () => false })
  renderPage()
  await issueFlow()
  expect(await screen.findByText('网络不可用，没有产生令牌。')).toBeInTheDocument()
  expect(screen.queryByTestId('issued-plaintext')).not.toBeInTheDocument()
})

test('usage unknown renders placeholder not zero', async () => {
  ;(fetchRelayPage as jest.Mock).mockResolvedValue({
    ...PAGE_WITH_TOKEN,
    tokens: [{ ...TOKEN, used_tokens: null }],
  })
  renderPage()
  await screen.findByText('prod')
  await waitFor(() => {
    expect(screen.queryByText('1,200')).not.toBeInTheDocument()
  })
  expect(screen.getByText('—')).toBeInTheDocument()
})

test('GWT-U21.1 / GWT-M23.2 SKU none shows only 未开通中转, no token empty, no groups empty', async () => {
  ;(fetchRelaySku as jest.Mock).mockResolvedValue(SKU_NONE)
  renderPage()
  expect(await screen.findByText('未开通中转')).toBeInTheDocument()
  expect(screen.queryByText('还没有令牌')).not.toBeInTheDocument()
  expect(screen.queryByText('还没有渠道组。创建后才能签发令牌。')).not.toBeInTheDocument()
  expect(screen.queryByText('default')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: ISSUE_BUTTON })).not.toBeInTheDocument()
  expect(screen.queryByText('已开通')).not.toBeInTheDocument()
  expect(screen.queryByText('使用中')).not.toBeInTheDocument()
  expect(document.body.textContent).not.toContain('当前可买')
  fireEvent.click(screen.getByRole('button', { name: '去升级' }))
  expect(await screen.findByTestId('checkout-probe')).toHaveTextContent('relay')
  expect(screen.queryByText('register-probe')).toBeNull()
  expect(fetchRelayPage).not.toHaveBeenCalled()
})

test('GWT-U35.7 operator 去升级 is contact admin, not checkout', async () => {
  mockUserState.current = OPERATOR
  ;(fetchRelaySku as jest.Mock).mockResolvedValue(SKU_NONE_OPERATOR)
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: '去升级' }))
  expect(await screen.findByText(CONTACT_ADMIN_COPY)).toBeInTheDocument()
  expect(screen.queryByTestId('checkout-probe')).toBeNull()
})

test('GWT-U23.4 SKU expired shows 中转已到期, no issue', async () => {
  ;(fetchRelaySku as jest.Mock).mockResolvedValue(SKU_EXPIRED)
  renderPage()
  expect(await screen.findByText('中转已到期')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: ISSUE_BUTTON })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: '去升级' })).toBeInTheDocument()
})

test('GWT-U20.1 active lists own usage, no upstream key, not duty page', async () => {
  ;(fetchRelayPage as jest.Mock).mockResolvedValue(PAGE_WITH_TOKEN)
  renderPage()
  expect(await screen.findByText('1,200')).toBeInTheDocument()
  expect(screen.getByTestId('relay-active')).toBeInTheDocument()
  expect(document.body.textContent || '').not.toContain('master')
  expect(screen.queryByText('中转站管控')).not.toBeInTheDocument()
  expect(screen.queryByRole('link', { name: /newapi/i })).not.toBeInTheDocument()
})

test('GWT-M23.1 plan_pro unopened is 未开通中转, no token list', async () => {
  ;(fetchRelaySku as jest.Mock).mockResolvedValue(SKU_NONE)
  renderPage()
  expect(await screen.findByText('未开通中转')).toBeInTheDocument()
  expect(screen.queryByTestId('relay-active')).not.toBeInTheDocument()
  expect(fetchRelayPage).not.toHaveBeenCalled()
})

test('relay unopened does not print 开通处理中 as a second Then', async () => {
  ;(fetchRelaySku as jest.Mock).mockResolvedValue(SKU_NONE)
  ;(listMyOrders as jest.Mock).mockResolvedValue([
    { id: 3, status: 'paid_pending_fulfillment', product_code: 'relay', channel: 'alipay', amount_cents: 9900 },
  ])
  renderPage()
  expect(await screen.findByText('未开通中转')).toBeInTheDocument()
  expect(screen.queryByText('开通处理中')).not.toBeInTheDocument()
  expect(screen.queryByText('支付已到账，开通处理中')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: ISSUE_BUTTON })).not.toBeInTheDocument()
})

