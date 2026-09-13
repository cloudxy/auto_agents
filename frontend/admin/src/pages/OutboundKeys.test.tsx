/**
 * T-06 出站拉数钥匙页：GWT-51.2 空态句（信封 message 单源）+有权签发入口；
 * GWT-51.1 签发明文只一次；GWT-51.8 再进页只见前缀+状态；
 * GWT-51.5/51.9 只读无控件+「请联系企业管理员」（控件隐藏单支）；
 * 吊销确认弹窗（不可逆提示）；FR-84 族失败≠空表；超管无企业=企业空间句。
 * 产品名纪律：除互斥说明句外不得出现「渠道组令牌」字样。
 */
import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import OutboundKeys from './OutboundKeys'

jest.mock('../services/outboundKeys', () => ({
  fetchOutboundKeys: jest.fn(),
  issueOutboundKey: jest.fn(),
  revokeOutboundKey: jest.fn(),
}))

// babel-jest 工厂引用 mock* 前缀变量（render 时才读取，无 TDZ）
const mockUserState: { current: Record<string, unknown> | null } = {
  current: null,
}

jest.mock('../store/useAuthStore', () => ({
  useAuthStore: (sel: (s: { user: Record<string, unknown> | null }) => unknown) =>
    sel({ user: mockUserState.current }),
}))

import { fetchOutboundKeys, issueOutboundKey, revokeOutboundKey } from '../services/outboundKeys'

const OWNER = { tenant_id: 1, tenant_role: 'owner', is_platform_admin: false }
const OPERATOR = { tenant_id: 1, tenant_role: 'operator', is_platform_admin: false }
const VIEWER = { tenant_id: 1, tenant_role: 'viewer', is_platform_admin: false }

const KEY = {
  id: 7, name: 'bi', key_prefix: 'ok-XyZaBc', status: 'active',
  revoked_at: null, created_at: '2026-09-11T02:03:04Z',
}
const LIST_WITH_KEY = { keys: [KEY], message: '操作成功' }
const LIST_REVOKED = {
  keys: [{ ...KEY, status: 'revoked', revoked_at: '2026-09-11T03:00:00Z' }],
  message: '操作成功',
}
const EMPTY_LIST = {
  keys: [],
  message: '还没有出站拉数钥匙。签发后才能从外部系统拉本企业结果。',
}

// 票面钉的两字按钮形态 /签\s*发/（antd 两字按钮自动插空格：签 发 / 吊 销）
const ISSUE_BUTTON = /签\s*发/
const MODAL_OK_ISSUE = /^签\s*发$/
const REVOKE_BUTTON = /吊\s*销/

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <OutboundKeys />
    </QueryClientProvider>,
  )
}

async function issueFlow() {
  fireEvent.click(await screen.findByRole('button', { name: /签\s*发出站拉数钥匙/ }))
  fireEvent.click(screen.getByRole('button', { name: MODAL_OK_ISSUE }))
}

beforeEach(() => {
  jest.clearAllMocks()
  mockUserState.current = OPERATOR
})

test('gwt_51_2: empty sentence from envelope with issue entry for entitled role, not a relay page', async () => {
  ;(fetchOutboundKeys as jest.Mock).mockResolvedValue(EMPTY_LIST)
  renderPage()
  expect(await screen.findByText('还没有出站拉数钥匙。签发后才能从外部系统拉本企业结果。')).toBeInTheDocument()
  // 有权者（经办）见签发（工具栏 + 空态动作）；不是默认「暂无数据」
  expect(screen.getAllByRole('button', { name: ISSUE_BUTTON }).length).toBeGreaterThan(0)
  expect(screen.queryByText('暂无数据')).not.toBeInTheDocument()
  // 不冒充渠道组页：无渠道组空态句、无渠道组操作
  expect(screen.queryByText(/还没有令牌/)).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /新\s*建\s*渠\s*道\s*组/ })).not.toBeInTheDocument()
})

test('gwt_51_5_51_9: viewer sees list with note, no issue/revoke controls', async () => {
  ;(fetchOutboundKeys as jest.Mock).mockResolvedValue(LIST_WITH_KEY)
  mockUserState.current = VIEWER
  renderPage()
  expect(await screen.findByText(/ok-XyZaBc/)).toBeInTheDocument()
  expect(screen.getByText('已签发')).toBeInTheDocument()
  // 控件隐藏单支（QA-09）：无签发/吊销控件 + 页上「请联系企业管理员」说明句
  expect(screen.getByText('请联系企业管理员')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: ISSUE_BUTTON })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: REVOKE_BUTTON })).not.toBeInTheDocument()
})

test('gwt_51_1_51_8: issue shows plaintext once, revisit shows prefix and status only', async () => {
  ;(fetchOutboundKeys as jest.Mock)
    .mockResolvedValueOnce(EMPTY_LIST)
    .mockResolvedValue(LIST_WITH_KEY) // 再进页：列表无明文，只有前缀+状态
  ;(issueOutboundKey as jest.Mock).mockResolvedValue({ ...KEY, plaintext_key: 'ok-SecretPlaintext123' })
  renderPage()
  await issueFlow()
  expect(await screen.findByText('请立即复制出站拉数钥匙')).toBeInTheDocument()
  expect(await screen.findByTestId('issued-plaintext')).toHaveTextContent('ok-SecretPlaintext123')
  expect(screen.getByText(/明文仅显示一次，请妥善保存/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /我已保存/ }))
  // 明文随弹窗消失（含关闭动画），列表只剩前缀+状态（GWT-51.8）
  expect(await screen.findByText(/ok-XyZaBc/)).toBeInTheDocument()
  await waitFor(() => {
    expect(screen.queryByText(/ok-SecretPlaintext123/)).not.toBeInTheDocument()
  })
  expect(screen.getByText('已签发')).toBeInTheDocument()
})

test('revoke confirm modal shows irreversible copy, then key becomes revoked', async () => {
  ;(fetchOutboundKeys as jest.Mock)
    .mockResolvedValueOnce(LIST_WITH_KEY)
    .mockResolvedValue(LIST_REVOKED)
  ;(revokeOutboundKey as jest.Mock).mockResolvedValue({ ...KEY, status: 'revoked' })
  mockUserState.current = OWNER
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: REVOKE_BUTTON }))
  // 吊销确认弹窗：不可逆提示中文
  expect(await screen.findByText('吊销这把出站拉数钥匙？')).toBeInTheDocument()
  expect(screen.getByText(/不可恢复/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /确认吊销/ }))
  expect(await screen.findByText('已吊销')).toBeInTheDocument()
  expect(revokeOutboundKey).toHaveBeenCalledWith(7, expect.anything())
})

test('gwt_84: load failure shows retry sentence, not an empty table', async () => {
  ;(fetchOutboundKeys as jest.Mock).mockRejectedValue(new Error('network down'))
  renderPage()
  expect(await screen.findByText('出站拉数钥匙加载失败。检查网络后重试。')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /重\s*试/ })).toBeInTheDocument()
  expect(screen.queryByText('暂无数据')).not.toBeInTheDocument()
  expect(screen.queryByText(/还没有出站拉数钥匙/)).not.toBeInTheDocument()
})

test('issue failure stays inline, modal open, no fake success plaintext', async () => {
  ;(fetchOutboundKeys as jest.Mock).mockResolvedValue(EMPTY_LIST)
  ;(issueOutboundKey as jest.Mock).mockRejectedValue({
    response: { data: { code: 'OUTBOUND_KEY_ROLE_NOT_ALLOWED', message: '请联系企业管理员' } },
  })
  renderPage()
  await issueFlow()
  expect(await screen.findByText('签发失败。请联系企业管理员。没有产生钥匙。')).toBeInTheDocument()
  // 弹窗不关（标题仍在）、无明文、无假成功
  expect(document.querySelector('.ant-modal-title')?.textContent).toContain('签发出站拉数钥匙')
  expect(screen.queryByTestId('issued-plaintext')).not.toBeInTheDocument()
})

test('issue offline shows offline sentence and no plaintext', async () => {
  ;(fetchOutboundKeys as jest.Mock).mockResolvedValue(EMPTY_LIST)
  const onlineSpy = jest.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(false)
  renderPage()
  await issueFlow()
  expect(await screen.findByText('网络不可用，没有产生钥匙。')).toBeInTheDocument()
  expect(screen.queryByTestId('issued-plaintext')).not.toBeInTheDocument()
  onlineSpy.mockRestore()
})

test('revoke failure stays inline in modal: key still usable', async () => {
  ;(fetchOutboundKeys as jest.Mock).mockResolvedValue(LIST_WITH_KEY)
  ;(revokeOutboundKey as jest.Mock).mockRejectedValue(new Error('boom'))
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: REVOKE_BUTTON }))
  fireEvent.click(await screen.findByRole('button', { name: /确认吊销/ }))
  expect(await screen.findByText('吊销失败。钥匙仍可使用。')).toBeInTheDocument()
  // 弹窗不关：仍处于确认态，可取消
  expect(document.querySelector('.ant-modal-title')?.textContent).toContain('吊销这把出站拉数钥匙')
})

test('platform admin without tenant sees tenant-space note and sends no list request', async () => {
  mockUserState.current = { tenant_id: null, tenant_role: null, is_platform_admin: true }
  renderPage()
  expect(await screen.findByText('出站拉数属于企业空间')).toBeInTheDocument()
  expect(fetchOutboundKeys).not.toHaveBeenCalled()
  expect(screen.queryByText(/还没有出站拉数钥匙/)).not.toBeInTheDocument()
})
