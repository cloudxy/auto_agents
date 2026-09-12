/**
 * T-10 渠道组页：GWT-60.1 签发明文一次+同屏 Base URL/三步；60.2 只读见用量；
 * 60.4 无令牌空态句（信封 message 单一来源）；60.7 经办找管理员句非空表；
 * 60.11 再进页只见前缀+状态；GWT-84.1 失败≠空表；签发失败内联可见。
 */
import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import RelayGroups from './RelayGroups'

jest.mock('../services/relay', () => ({
  fetchRelayPage: jest.fn(),
  createRelayGroup: jest.fn(),
  patchRelayGroup: jest.fn(),
  issueRelayToken: jest.fn(),
  revokeRelayToken: jest.fn(),
}))

// babel-jest 工厂引用 mock* 前缀变量（render 时才读取，无 TDZ）
const mockUserState: { current: Record<string, unknown> | null } = {
  current: null,
}

jest.mock('../store/useAuthStore', () => ({
  useAuthStore: (sel: (s: { user: Record<string, unknown> | null }) => unknown) =>
    sel({ user: mockUserState.current }),
}))

import { fetchRelayPage, issueRelayToken } from '../services/relay'

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
  tokensMessage: '还没有令牌。签发后才能按下方用法调用平台网关。',
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
      <RelayGroups />
    </QueryClientProvider>,
  )
}

async function issueFlow() {
  fireEvent.click(await screen.findByRole('button', { name: ISSUE_BUTTON }))
  fireEvent.change(screen.getByLabelText('备注名'), { target: { value: 'prod' } })
  fireEvent.click(screen.getByRole('button', { name: MODAL_OK_ISSUE }))
}

beforeEach(() => {
  jest.clearAllMocks()
  mockUserState.current = OWNER
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
  expect(screen.getByText('已签发')).toBeInTheDocument()
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

test('gwt_60_4: no tokens empty sentence with issue entry; usage area still rendered', async () => {
  ;(fetchRelayPage as jest.Mock).mockResolvedValue(EMPTY_PAGE)
  renderPage()
  expect(await screen.findByText('还没有令牌。签发后才能按下方用法调用平台网关。')).toBeInTheDocument()
  expect(screen.getByText('还没有渠道组。创建后才能签发令牌。')).toBeInTheDocument()
  expect(screen.getByTestId('relay-usage')).toBeInTheDocument()
  // 有权者看见签发（工具栏 + 空态动作）；不是默认「暂无数据」
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
  const onlineSpy = jest.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(false)
  renderPage()
  await issueFlow()
  expect(await screen.findByText('网络不可用，没有产生令牌。')).toBeInTheDocument()
  expect(screen.queryByTestId('issued-plaintext')).not.toBeInTheDocument()
  onlineSpy.mockRestore()
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
