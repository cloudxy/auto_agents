/**
 * LLM 供应商页（FR-97 / T-30 + 既有回归）：
 * - GWT-97.1 全页用户可见面无「激活」，说明句/横幅/筛选位钉句呈现
 * - GWT-97.2 设为默认确认弹窗钉句 + 互斥呈现 + 成功反馈；失败/离线内联弹窗不关
 * - GWT-97.4 只读无「设为默认」控件，默认标记可见；SHAPE-QA-03 经办 CRUD 保持但无设默认
 * - GWT-97.3 空态钉句 / 失败句不走空态；既有 GWT-73.4/06.5 回归
 */
import React from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';

jest.mock('../components/llm/ProviderWizardModal', () => ({
  __esModule: true,
  default: () => null,
}))
jest.mock('../components/llm/ModelSetDrawer', () => ({
  __esModule: true,
  default: () => null,
}))

jest.mock('../hooks/usePermission', () => ({
  usePermission: jest.fn(() => ({
    hasPermission: () => false,
    isPlatformAdmin: false,
    role: 'viewer',
    isAdmin: false,
    permissions: [],
    permissionsReady: true,
    filteredMenus: [],
  })),
}))

jest.mock('../services/llm', () => ({
  fetchLlmProviders: jest.fn(),
  fetchActiveLlmProvider: jest.fn(),
  getPlatformPresets: jest.fn().mockResolvedValue([]),
  createLlmProvider: jest.fn(),
  updateLlmProvider: jest.fn(),
  deleteLlmProvider: jest.fn(),
  activateLlmProvider: jest.fn(),
  deactivateLlmProvider: jest.fn(),
  testLlmProvider: jest.fn(),
  probeModels: jest.fn(),
  probeTest: jest.fn(),
  getLlmProviderModels: jest.fn().mockResolvedValue([
    { model_id: 'claude-sonnet-4-6', alias: '', model_tier: 'strong', priority: 10, is_default: true, enabled: true, health_status: 'healthy' },
    { model_id: 'claude-haiku-4-5', alias: '', model_tier: 'basic', priority: 50, is_default: false, enabled: true, health_status: 'unknown' },
  ]),
  putLlmProviderModels: jest.fn(),
  fetchModelsDiff: jest.fn(),
  testLlmProviderModel: jest.fn(),
}));

import LlmProviders from './LlmProviders';
import { usePermission } from '../hooks/usePermission';
import { fetchLlmProviders, fetchActiveLlmProvider, activateLlmProvider, deactivateLlmProvider, testLlmProvider } from '../services/llm';
import { useAuthStore } from '../store/useAuthStore';
import type { LoginResponse } from '../services/auth';

const mockedPerm = usePermission as jest.Mock

// 与 jest.mock 工厂内联默认同形（工厂变量受 hoist 限制，运行时恢复用此份）
const VIEWER_PERM = {
  hasPermission: () => false,
  isPlatformAdmin: false,
  role: 'viewer',
  isAdmin: false,
  permissions: [],
  permissionsReady: true,
  filteredMenus: [],
}

// 租户角色经 useAuthStore（与 RelayGroups _ISSUER_ROLES 同口径：owner/admin 可设默认）
const setUser = (partial: Partial<LoginResponse>) =>
  act(() => {
    useAuthStore.setState({
      user: { access_token: 't', token_type: 'Bearer', username: 'u', is_admin: false, ...partial },
    })
  })

afterEach(() => {
  act(() => { useAuthStore.setState({ user: null }) })
  jest.clearAllMocks()
  // clearAllMocks 不清除实现：显式恢复只读默认，避免 PERM_OWNER 泄漏到后续用例
  mockedPerm.mockReturnValue(VIEWER_PERM)
  ;(fetchLlmProviders as jest.Mock).mockReset()
  ;(fetchActiveLlmProvider as jest.Mock).mockReset()
})

const PERM_OWNER = {
  hasPermission: (c: string) => c === 'btn:create' || c === 'btn:delete',
  isPlatformAdmin: false,
  role: 'admin',
  isAdmin: true,
  permissions: ['btn:create', 'btn:delete'],
  permissionsReady: true,
  filteredMenus: [],
}

const PROV_A = {
  id: 1, name: '主用', provider_type: 'anthropic', base_url: 'https://a.example/v1',
  model: 'claude-sonnet-4-6', enabled: true, is_active: true, tenant_id: 9, api_key_masked: '***a',
}
const PROV_B = {
  id: 2, name: '备用', provider_type: 'openai_compatible', base_url: 'https://b.example/v1',
  model: 'gpt-x', enabled: true, is_active: false, tenant_id: 9, api_key_masked: '***b',
}

const rowOf = (name: string) => screen.getByText(name).closest('tr') as HTMLElement

const renderOwner = (providers: unknown[], active: unknown) => {
  mockedPerm.mockReturnValue(PERM_OWNER)
  setUser({ tenant_role: 'owner', tenant_id: 9 })
  ;(fetchLlmProviders as jest.Mock).mockResolvedValue(providers)
  ;(fetchActiveLlmProvider as jest.Mock).mockResolvedValue(active)
  render(<LlmProviders />)
}

// ---------------- GWT-97.1 文案 ----------------

test('owner surface uses 默认/设为默认 only — no 激活 anywhere (GWT-97.1)', async () => {
  renderOwner([PROV_A, PROV_B], PROV_A)
  expect(await screen.findByText('主用')).toBeInTheDocument()
  // 说明句（钉句）
  expect(screen.getByText('未指定模型时，默认使用该模型，可按需更换。')).toBeInTheDocument()
  // 横幅改「当前默认供应商」
  expect(screen.getByText(/当前默认供应商：主用（claude-sonnet-4-6）/)).toBeInTheDocument()
  // 非默认行动作「设为默认」、默认行「取消默认」
  expect(within(rowOf('备用')).getByText('设为默认')).toBeInTheDocument()
  expect(within(rowOf('主用')).getByText('取消默认')).toBeInTheDocument()
  // 已有默认 → 不出未设默认提示
  expect(screen.queryByText(/还没有默认供应商/)).toBeNull()
  // 全页用户可见面无「激活」（代码标识符不算）
  expect(document.body.textContent || '').not.toContain('激活')
})

test('default model tag keeps gold tag and 未指定模型时使用 hint', async () => {
  renderOwner([PROV_A, PROV_B], PROV_A)
  const row = (await screen.findByText('主用')).closest('tr') as HTMLElement
  fireEvent.mouseEnter(within(row).getByText('claude-sonnet-4-6'))
  expect(await screen.findByText('未指定模型时使用')).toBeInTheDocument()
})

// ---------------- GWT-97.2 设为默认：确认弹窗 + 互斥 + 失败/离线 ----------------

test('set default confirm modal uses pinned sentence, then mutual exclusion (GWT-97.2)', async () => {
  renderOwner([PROV_A, PROV_B], PROV_A)
  expect(await screen.findByText('主用')).toBeInTheDocument()
  fireEvent.click(within(rowOf('备用')).getByText('设为默认'))
  // 切换确认钉句（含 A 不再默认半句）
  expect(await screen.findByText('将“备用”设为默认？未指定模型的请求将默认使用它；“主用”不再默认。')).toBeInTheDocument()
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '设为默认' }))
  await waitFor(() => expect(activateLlmProvider).toHaveBeenCalledWith(2))
  expect(await screen.findByText(/已将“备用”设为默认。/)).toBeInTheDocument()
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  // 互斥呈现：刷新拿到 B 默认/A 不默认 → B 带默认标记、A 标记消失（同域至多一个）
  ;(fetchLlmProviders as jest.Mock).mockResolvedValue([
    { ...PROV_A, is_active: false },
    { ...PROV_B, is_active: true },
  ])
  ;(fetchActiveLlmProvider as jest.Mock).mockResolvedValue({ ...PROV_B, is_active: true })
  fireEvent.click(screen.getByText('刷新'))
  await waitFor(() => expect(within(rowOf('备用')).getByText('默认')).toBeInTheDocument())
  expect(within(rowOf('主用')).queryByText('默认')).toBeNull()
})

test('set default failure keeps modal open with inline sentence (edge-states 错误)', async () => {
  renderOwner([PROV_A, PROV_B], PROV_A)
  expect(await screen.findByText('主用')).toBeInTheDocument()
  fireEvent.click(within(rowOf('备用')).getByText('设为默认'))
  ;(activateLlmProvider as jest.Mock).mockRejectedValueOnce({ response: { data: { message: '服务暂不可用' } } })
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '设为默认' }))
  expect(await screen.findByText('设置默认失败。服务暂不可用。原默认保持不变。')).toBeInTheDocument()
  expect(screen.getByRole('dialog')).toBeInTheDocument()
})

test('set default offline keeps modal open with offline sentence', async () => {
  const onlineSpy = jest.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(false)
  renderOwner([PROV_A, PROV_B], PROV_A)
  expect(await screen.findByText('主用')).toBeInTheDocument()
  fireEvent.click(within(rowOf('备用')).getByText('设为默认'))
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '设为默认' }))
  expect(await screen.findByText('网络不可用，默认没有更改。')).toBeInTheDocument()
  expect(screen.getByRole('dialog')).toBeInTheDocument()
  expect(activateLlmProvider).not.toHaveBeenCalled()
  onlineSpy.mockRestore()
})

test('cancel default calls deactivate and shows no-default hint after', async () => {
  renderOwner([PROV_A, PROV_B], PROV_A)
  expect(await screen.findByText('主用')).toBeInTheDocument()
  fireEvent.click(within(rowOf('主用')).getByText('取消默认'))
  expect(await screen.findByText('取消默认“主用”？')).toBeInTheDocument()
  ;(deactivateLlmProvider as jest.Mock).mockResolvedValueOnce({ ...PROV_A, is_active: false })
  const popover = await waitFor(() => {
    const pop = document.querySelector('.ant-popover') as HTMLElement
    expect(pop).toBeTruthy()
    return pop
  })
  fireEvent.click(within(popover).getByRole('button', { name: '取消默认' }))
  await waitFor(() => expect(deactivateLlmProvider).toHaveBeenCalledWith(1))
  expect(await screen.findByText(/已取消“主用”的默认。/)).toBeInTheDocument()
  // 刷新拿到无默认列表 → 表格上方一行文字提示（非横幅）
  ;(fetchLlmProviders as jest.Mock).mockResolvedValue([{ ...PROV_A, is_active: false }, PROV_B])
  ;(fetchActiveLlmProvider as jest.Mock).mockResolvedValue(null)
  fireEvent.click(screen.getByText('刷新'))
  await waitFor(() => expect(screen.getByText('还没有默认供应商。未指定模型的请求将使用平台公共模型。')).toBeInTheDocument())
})

// ---------------- T-34 / GWT-99.1 页头规范 ----------------

test('page header spec: no in-page title card or banner; banner info lives in content (GWT-99.1/99.4)', async () => {
  renderOwner([PROV_A, PROV_B], PROV_A)
  expect(await screen.findByText('主用')).toBeInTheDocument()
  // 无 h1/标题卡复述页名，无「LLM 供应商配置」Card title
  expect(screen.queryByRole('heading')).toBeNull()
  expect(screen.queryByText('LLM 供应商配置')).toBeNull()
  expect(screen.queryByText('LLM 配置')).toBeNull()
  // 绿色「当前默认供应商」横幅移除：无 success Alert，信息量以内容行承担（GWT-99.4）
  expect(document.querySelector('.ant-alert-success')).toBeNull()
  expect(screen.getByText(/当前默认供应商：主用（claude-sonnet-4-6）/)).toBeInTheDocument()
  // 内容区第一屏即业务内容：说明句 + 供应商表 + 动作（GWT-99.3 等价）
  expect(screen.getByRole('table')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /新建供应商/ })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /刷\s*新/ })).toBeInTheDocument()
})

// ---------------- GWT-97.3 空态 / 失败句 ----------------

test('empty state pins 还没有模型供应商 with 添加供应商 for authorized (GWT-97.3)', async () => {
  renderOwner([], null)
  expect(await screen.findByText('还没有模型供应商。')).toBeInTheDocument()
  expect(screen.getByText('添加供应商')).toBeInTheDocument()
  expect(screen.queryByText(/暂无 LLM 供应商/)).toBeNull()
})

test('readonly empty state shows sentence without 添加供应商', async () => {
  ;(fetchLlmProviders as jest.Mock).mockResolvedValue([])
  ;(fetchActiveLlmProvider as jest.Mock).mockResolvedValue(null)
  render(<LlmProviders />)
  expect(await screen.findByText('还没有模型供应商。')).toBeInTheDocument()
  expect(screen.queryByText('添加供应商')).toBeNull()
})

test('list failure shows failure sentence, not empty state (GWT-97.3 / FR-84)', async () => {
  ;(fetchLlmProviders as jest.Mock).mockRejectedValue(new Error('x'))
  ;(fetchActiveLlmProvider as jest.Mock).mockResolvedValue(null)
  render(<LlmProviders />)
  expect(await screen.findByText('供应商列表加载失败。检查网络后重试。')).toBeInTheDocument()
  // antd 两字按钮渲染带空格（「重 试」）；句中「重试」无空格，用 role 区分
  expect(screen.getByRole('button', { name: /重\s*试/ })).toBeInTheDocument()
  expect(screen.queryByText('还没有模型供应商。')).toBeNull()
})

// ---------------- GWT-97.4 / SHAPE-QA-03 角色显隐 ----------------

test('readonly member sees default mark, no set-default controls (GWT-97.4)', async () => {
  ;(fetchLlmProviders as jest.Mock).mockResolvedValue([PROV_A, PROV_B])
  ;(fetchActiveLlmProvider as jest.Mock).mockResolvedValue(PROV_A)
  render(<LlmProviders />)
  expect(await screen.findByText('主用')).toBeInTheDocument()
  // 默认标记可见；无「设为默认/取消默认」控件
  expect(within(rowOf('主用')).getByText('默认')).toBeInTheDocument()
  expect(screen.queryByText('设为默认')).toBeNull()
  expect(screen.queryByText('取消默认')).toBeNull()
  // 只读旁注沿用
  expect(screen.getByText(/当前账号不能管理供应商/)).toBeInTheDocument()
  expect(screen.queryByText(/当前账号不能设置默认/)).toBeNull()
})

test('operator keeps CRUD write but no set-default control (SHAPE-QA-03)', async () => {
  mockedPerm.mockReturnValue({
    hasPermission: (c: string) => c === 'btn:create' || c === 'btn:delete',
    isPlatformAdmin: false,
    role: 'operator',
    isAdmin: false,
    permissions: ['btn:create', 'btn:delete'],
    permissionsReady: true,
    filteredMenus: [],
  })
  setUser({ tenant_role: 'operator', tenant_id: 9 })
  ;(fetchLlmProviders as jest.Mock).mockResolvedValue([PROV_A, PROV_B])
  ;(fetchActiveLlmProvider as jest.Mock).mockResolvedValue(PROV_A)
  render(<LlmProviders />)
  expect(await screen.findByText('主用')).toBeInTheDocument()
  // 既有本企业行 CRUD 写权保持
  expect(screen.getByText('新建供应商')).toBeInTheDocument()
  expect(within(rowOf('主用')).getByText('测试连接')).toBeInTheDocument()
  expect(within(rowOf('主用')).getByText('编辑')).toBeInTheDocument()
  expect(within(rowOf('主用')).getByText('管理模型')).toBeInTheDocument()
  // 「设为默认」收权到负责人/公司管理员：经办无控件，只有旁注
  expect(screen.queryByText('设为默认')).toBeNull()
  expect(screen.queryByText('取消默认')).toBeNull()
  expect(screen.getByText('当前账号不能设置默认，请联系企业管理员')).toBeInTheDocument()
})

// ---------------- 既有回归（GWT-06.5 / GWT-73.4） ----------------

test('renders provider list with protocol display name and readonly guard', async () => {
  ;(fetchLlmProviders as jest.Mock).mockResolvedValue([
    { id: 1, name: '主用', provider_type: 'anthropic', base_url: 'https://api.anthropic.com',
      model: 'claude-sonnet-4-6', enabled: true, is_active: true, api_key_masked: 'sk-***' },
  ])
  ;(fetchActiveLlmProvider as jest.Mock).mockResolvedValue(
    { id: 1, name: '主用', model: 'claude-sonnet-4-6', is_active: true, enabled: true },
  )
  render(<LlmProviders />)
  expect(await screen.findByText('主用')).toBeInTheDocument()
  expect(screen.getByText('Anthropic 原生')).toBeInTheDocument(); // 协议显示名（不再是裸枚举值）
  expect(screen.getByText(/当前账号不能管理供应商/)).toBeInTheDocument();
  expect(screen.queryByText('新建供应商')).toBeNull();
  expect(screen.queryByText('管理模型')).toBeNull();
  expect(screen.queryByText('测试连接')).toBeNull();
})

test('tenant admin sees own-row write, hides platform-row write (GWT-06.5)', async () => {
  mockedPerm.mockReturnValue({
    hasPermission: (c: string) => c === 'btn:create' || c === 'btn:delete',
    isPlatformAdmin: false,
    role: 'admin',
    isAdmin: true,
    permissions: ['btn:create', 'btn:delete'],
    permissionsReady: true,
    filteredMenus: [],
  })
  setUser({ tenant_role: 'admin', tenant_id: 9 })
  ;(fetchLlmProviders as jest.Mock).mockResolvedValue([PROV_A, { ...PROV_B, tenant_id: null, name: '平台公共' }])
  ;(fetchActiveLlmProvider as jest.Mock).mockResolvedValue(PROV_A)
  render(<LlmProviders />)
  expect(await screen.findByText('主用')).toBeInTheDocument()
  expect(screen.getByText('平台公共')).toBeInTheDocument()
  expect(screen.getByText('平台')).toBeInTheDocument()
  expect(screen.getByText('新建供应商')).toBeInTheDocument()
  expect(screen.getAllByText('测试连接')).toHaveLength(1)
  // 公司管理员（tenant_role=admin，GWT-97.1/97.2 主语）：本企业行有默认控件，平台行无
  expect(within(rowOf('主用')).getByText('取消默认')).toBeInTheDocument()
  expect(within(rowOf('平台公共')).queryByText('设为默认')).toBeNull()
})

test('operator sees save and 测试连接 on own row (GWT-73.4 click)', async () => {
  mockedPerm.mockReturnValue({
    hasPermission: (c: string) => c === 'btn:create' || c === 'menu:llm',
    isPlatformAdmin: false,
    role: 'operator',
    isAdmin: false,
    permissions: ['btn:create', 'menu:llm'],
    permissionsReady: true,
    filteredMenus: [],
  })
  setUser({ tenant_role: 'operator', tenant_id: 9 })
  ;(fetchLlmProviders as jest.Mock).mockResolvedValue([PROV_A, { ...PROV_B, tenant_id: null, name: '平台公共' }])
  ;(fetchActiveLlmProvider as jest.Mock).mockResolvedValue(PROV_A)
  render(<LlmProviders />)
  expect(await screen.findByText('主用')).toBeInTheDocument()
  // T-34 标题断言改内容断言：页内不再有 h1「LLM 配置」（页名唯一标题在顶栏），
  // 内容区直接以说明句行开始
  expect(screen.queryByRole('heading', { name: 'LLM 配置' })).toBeNull()
  expect(screen.getByText('未指定模型时，默认使用该模型，可按需更换。')).toBeInTheDocument()
  expect(screen.getByText('新建供应商')).toBeInTheDocument()
  expect(screen.queryByText(/当前账号不能管理供应商/)).toBeNull()
  expect(screen.getAllByText('测试连接')).toHaveLength(1)
})

test('operator click 测试连接 probes own-row id; fail copy is 本企业行 (GWT-73.4)', async () => {
  mockedPerm.mockReturnValue({
    hasPermission: (c: string) => c === 'btn:create' || c === 'menu:llm',
    isPlatformAdmin: false,
    role: 'operator',
    isAdmin: false,
    permissions: ['btn:create', 'menu:llm'],
    permissionsReady: true,
    filteredMenus: [],
  })
  setUser({ tenant_role: 'operator', tenant_id: 9 })
  ;(fetchLlmProviders as jest.Mock).mockResolvedValue([PROV_A, { ...PROV_B, tenant_id: null, name: '平台公共' }])
  ;(fetchActiveLlmProvider as jest.Mock).mockResolvedValue(PROV_A)
  ;(testLlmProvider as jest.Mock).mockResolvedValue({
    ok: false, error: '该行地址无响应', latency_ms: null, model: null,
  })
  render(<LlmProviders />)
  expect(await screen.findByText('主用')).toBeInTheDocument()
  fireEvent.click(screen.getByText('测试连接'))
  await waitFor(() => expect(testLlmProvider).toHaveBeenCalledWith(1))
  expect(testLlmProvider).not.toHaveBeenCalledWith(2)
  fireEvent.mouseEnter(await screen.findByText('失败'))
  await waitFor(() => {
    expect(document.body.textContent || '').toContain('连的是本企业供应商「主用」')
  })
  const failCopy = document.body.textContent || ''
  expect(failCopy).toContain('不是平台网关')
  expect(failCopy).not.toContain('还没有平台模型')
  expect(failCopy).not.toContain('平台 LLM 网关不可达')
  expect(failCopy).not.toContain('暂无渠道')
})
