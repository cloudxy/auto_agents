/**
 * T-15 / FR-82（ADR-0021 v2）组件测试：侧栏单一真相 + 组织幽灵页 404 同形。
 * - GWT-82.1 脏 /auth/menus 树（含角色权限/企业管理、缺渠道组/我的安装）不驱动侧栏：
 *   menuConfig + usePermission 权限过滤为唯一输入，侧栏生命周期不消费 /auth/menus。
 * - GWT-82.2 权限未就绪：「权限加载中」；渠道组/我的安装不永久消失；不闪组织幽灵叶。
 * - GWT-82.3 租户公司管理员直打 /rbac /enterprise = 缺页同形 404（无侧栏、非「抱歉」）；
 *   超管入口不砍（/enterprise /rbac 超管可达，ADR-0021 v2 和解句）。
 * - GWT-82.4 平台超管无企业空间打开渠道组/我的安装 = 「…属于企业空间」说明，
 *   不是空表假装没订阅（不因 FR-102 平台租户身份改变）。
 *
 * 注：菜单叶文案会与页头/卡片同名（pageTitleFor 派生），侧栏查询 within(sider) 限定。
 */
import React from 'react'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import api from './services/api'
import { useAuthStore } from './store/useAuthStore'
import { clearCachedPermissions } from './hooks/usePermission'

jest.mock('./services/api', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn(() => Promise.reject(new Error('mock network'))),
    put: jest.fn(() => Promise.reject(new Error('mock network'))),
    patch: jest.fn(() => Promise.reject(new Error('mock network'))),
    delete: jest.fn(() => Promise.reject(new Error('mock network'))),
  },
  unwrap: (r: unknown) => (r && typeof r === 'object' && 'data' in (r as Record<string, unknown>)
    ? (r as Record<string, unknown>).data
    : r),
}))

const envelope = (data: unknown) => ({ success: true, code: 'OK', message: 'ok', data })

/** 脏 DB 菜单树（种子 023 漂移形态）：带 rbac/enterprise 幽灵叶，缺渠道组/我的安装 */
const DIRTY_DB_TREE = [
  {
    key: '/system', label: '系统管理', icon: 'ToolOutlined', tenantOnly: false, children: [
      { key: '/rbac', label: '角色权限', tenantOnly: false, children: [] },
      { key: '/enterprise', label: '企业管理', tenantOnly: false, children: [] },
      { key: '/users', label: '用户管理', tenantOnly: false, children: [] },
    ],
  },
  {
    key: '/overview', label: '概览', icon: 'DashboardOutlined', tenantOnly: false, children: [
      { key: '/dashboard', label: '仪表盘', tenantOnly: false, children: [] },
    ],
  },
]

const TENANT_OWNER = {
  access_token: 't', token_type: 'bearer', username: 'owner',
  is_admin: true, role: 'admin', is_platform_admin: false, tenant_id: 3,
}

const TENANT_COMPANY_ADMIN = {
  access_token: 't', token_type: 'bearer', username: 'boss',
  is_admin: true, role: 'admin', is_platform_admin: false, tenant_id: 3,
}

const PLATFORM_SUPER_ADMIN_NO_TENANT = {
  access_token: 't', token_type: 'bearer', username: 'root',
  is_admin: true, role: 'admin', is_platform_admin: true, tenant_id: null,
}

/** 租户负责人全量读权限（平台写叶不在其列，本就 platformOnly 剥离） */
const TENANT_PERMS = [
  'menu:dashboard', 'menu:usage', 'menu:relay', 'menu:skills',
  'menu:spiders.tasks', 'menu:spiders.logs', 'menu:spiders.nodes',
  'menu:ai', 'menu:data', 'menu:members', 'menu:logs', 'menu:llm', 'menu:settings',
]

const login = (user: Record<string, unknown>) => {
  useAuthStore.setState({ token: 't', isAuthenticated: true, rememberMe: false, user: user as never })
}

beforeEach(() => {
  clearCachedPermissions()
  useAuthStore.setState({
    token: null, user: null, isAuthenticated: false, rememberMe: false,
  })
  ;(api.get as jest.Mock).mockReset()
  ;(api.get as jest.Mock).mockImplementation((url: string) => {
    if (url === '/auth/permissions') return Promise.resolve(envelope(TENANT_PERMS))
    if (url === '/auth/menus') return Promise.resolve(envelope(DIRTY_DB_TREE))
    if (url === '/public/capabilities' || url.startsWith('/public/capabilities')) {
      return Promise.resolve(envelope({
        items: [], total: 0, market_closed: false, message: '暂无已上架能力',
      }))
    }
    return Promise.reject(new Error('mock network'))
  })
})

const renderApp = (path: string) => {
  window.history.replaceState({}, '', path)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  )
}

const siderUI = (container: HTMLElement) =>
  within(container.querySelector('.ant-layout-sider') as HTMLElement)

const openGroup = async (
  ui: ReturnType<typeof within>, group: string, expectLeaf: string,
) => {
  fireEvent.click(ui.getByText(group))
  await ui.findByText(expectLeaf)
}

test('GWT-82.1 dirty /auth/menus tree does not drive the tenant sidebar', async () => {
  login(TENANT_OWNER)
  const { container } = renderApp('/dashboard')
  const ui = siderUI(container)

  await openGroup(ui, '概览', '仪表盘')
  expect(ui.getByText('我的渠道组')).toBeInTheDocument()
  await openGroup(ui, '能力资产', '能力市场')
  expect(ui.getByText('我的安装')).toBeInTheDocument()

  // 脏树里的组织幽灵叶：展开真实系统管理组后仍找不到
  await openGroup(ui, '系统管理', 'LLM 配置')
  expect(ui.queryByText('角色权限')).not.toBeInTheDocument()
  expect(ui.queryByText('企业管理')).not.toBeInTheDocument()

  // 停用驱动（ADR-0021 决策 1）：侧栏生命周期内不消费 /auth/menus
  expect(api.get).not.toHaveBeenCalledWith('/auth/menus')
})

test('GWT-82.2 permissions not ready: loading note, tenant leaves stay, no ghost flash', async () => {
  login(TENANT_OWNER)
  let resolvePerms!: (v: unknown) => void
  const deferred = new Promise((res) => { resolvePerms = res })
  ;(api.get as jest.Mock).mockImplementation((url: string) => {
    if (url === '/auth/permissions') return deferred
    if (url === '/auth/menus') return Promise.resolve(envelope(DIRTY_DB_TREE))
    return Promise.reject(new Error('mock network'))
  })

  const { container } = renderApp('/dashboard')
  const ui = siderUI(container)

  await openGroup(ui, '概览', '仪表盘')
  expect(ui.getByText('我的渠道组')).toBeInTheDocument()
  await openGroup(ui, '能力资产', '能力市场')
  expect(ui.getByText('我的安装')).toBeInTheDocument()

  expect(screen.getByText('权限加载中')).toBeInTheDocument()
  expect(screen.queryByText('角色权限')).not.toBeInTheDocument()
  expect(screen.queryByText('企业管理')).not.toBeInTheDocument()
  expect(ui.queryByText('中转站管控')).not.toBeInTheDocument()
  expect(ui.queryByText('平台运营台')).not.toBeInTheDocument()
  expect(ui.queryByText('用户管理')).not.toBeInTheDocument()
  expect(screen.queryByText('抱歉，您没有权限')).not.toBeInTheDocument()

  // 权限就绪：渠道组/我的安装不消失，「权限加载中」退场且不再回来
  await act(async () => { resolvePerms(envelope(TENANT_PERMS)) })
  await waitFor(() => expect(screen.queryByText('权限加载中')).not.toBeInTheDocument())
  expect(ui.getByText('我的渠道组')).toBeInTheDocument()
  expect(ui.getByText('我的安装')).toBeInTheDocument()
})

test('GWT-82.3 tenant company admin direct hit on /rbac is same 404 shell without sidebar', async () => {
  login(TENANT_COMPANY_ADMIN)
  renderApp('/rbac')

  expect(await screen.findByText('页面不存在或已被移除')).toBeInTheDocument()
  expect(await screen.findByRole('button', { name: /返回工作台/ })).toBeInTheDocument()
  expect(screen.queryByText(/抱歉/)).not.toBeInTheDocument()
  expect(screen.queryByText('AutoAgents')).not.toBeInTheDocument()
  expect(screen.queryByText(/渠道/)).not.toBeInTheDocument()
})

test('GWT-82.3 tenant company admin direct hit on /enterprise is same 404 shell, no other-company list', async () => {
  login(TENANT_COMPANY_ADMIN)
  renderApp('/enterprise')

  expect(await screen.findByText('页面不存在或已被移除')).toBeInTheDocument()
  expect(await screen.findByRole('button', { name: /返回工作台/ })).toBeInTheDocument()
  expect(screen.queryByText(/抱歉/)).not.toBeInTheDocument()
  expect(screen.queryByText('AutoAgents')).not.toBeInTheDocument()
  expect(screen.queryByText('新建公司')).not.toBeInTheDocument()
})

test('platform super admin still reaches /enterprise and /rbac (ADR-0021 v2)', async () => {
  login(PLATFORM_SUPER_ADMIN_NO_TENANT)

  const ent = renderApp('/enterprise')
  expect(await screen.findByText('新建公司')).toBeInTheDocument()
  expect(screen.getByText('AutoAgents')).toBeInTheDocument()
  expect(screen.queryByText('页面不存在或已被移除')).not.toBeInTheDocument()
  ent.unmount()

  const rbac = renderApp('/rbac')
  expect(await screen.findByText('角色权限菜单管理')).toBeInTheDocument()
  expect(screen.getByText('AutoAgents')).toBeInTheDocument()
  expect(screen.queryByText('页面不存在或已被移除')).not.toBeInTheDocument()
  rbac.unmount()
})

test('GWT-82.4 super admin without enterprise space on /relay: explanation, not a fake empty table', async () => {
  login(PLATFORM_SUPER_ADMIN_NO_TENANT)
  renderApp('/relay')

  expect(await screen.findByText('渠道组属于企业空间')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '新建渠道组' })).not.toBeInTheDocument()
})

test('GWT-82.4 super admin without enterprise space on /capabilities/installs: explanation, not empty subscription', async () => {
  login(PLATFORM_SUPER_ADMIN_NO_TENANT)
  renderApp('/capabilities/installs')

  expect(await screen.findByText('安装属于企业空间')).toBeInTheDocument()
  expect(screen.queryByText('去能力市场')).not.toBeInTheDocument()
  expect(screen.queryByText(/还没有订阅的能力/)).not.toBeInTheDocument()
})

test('tenant owner still gets the real relay page, not the enterprise-space note', async () => {
  login(TENANT_OWNER)
  renderApp('/relay')

  // T-10 后真实页写权按 tenant_role 判且数据失败走页内错误态（本套 api 全拒）：
  // 稳定判据 = RelayGroups 自有失败句（TenantSpaceOnly 无此句），企业空间说明态仍须缺席
  expect(await screen.findByText('渠道组加载失败。检查网络后重试。')).toBeInTheDocument()
  expect(screen.queryByText('渠道组属于企业空间')).not.toBeInTheDocument()
})

test('GWT-U15.2 permissions unknown keeps read leaves, not blank, not platform writes', async () => {
  login(TENANT_COMPANY_ADMIN)
  let resolvePerms!: (v: unknown) => void
  const deferred = new Promise((res) => { resolvePerms = res })
  ;(api.get as jest.Mock).mockImplementation((url: string) => {
    if (url === '/auth/permissions') return deferred
    if (url === '/public/capabilities' || url.startsWith('/public/capabilities')) {
      return Promise.resolve(envelope({
        items: [], total: 0, market_closed: false, message: '暂无已上架能力',
      }))
    }
    return Promise.reject(new Error('mock network'))
  })
  const { container } = renderApp('/capabilities')
  const ui = siderUI(container)
  expect(await screen.findByText('权限加载中')).toBeInTheDocument()
  expect(screen.getByText('AutoAgents')).toBeInTheDocument()
  expect(screen.queryByText('抱歉，您没有权限')).not.toBeInTheDocument()
  expect(screen.queryByText('抱歉您没有权限')).not.toBeInTheDocument()
  expect(screen.queryByRole('tab', { name: '源' })).not.toBeInTheDocument()
  expect(screen.queryByRole('tab', { name: '目录' })).not.toBeInTheDocument()
  expect(screen.queryByText('角色权限菜单管理')).not.toBeInTheDocument()
  expect(ui.queryByText('中转站管控')).not.toBeInTheDocument()
  expect(ui.queryByText('平台运营台')).not.toBeInTheDocument()
  expect(ui.queryByText('用户管理')).not.toBeInTheDocument()
  await openGroup(ui, '能力资产', '能力市场')
  expect(ui.getByText('我的安装')).toBeInTheDocument()
  await act(async () => { resolvePerms(envelope(TENANT_PERMS)) })
  await waitFor(() => expect(screen.queryByText('权限加载中')).not.toBeInTheDocument())
})

test('GWT-U21.2 我的渠道组 nav has no 已开通/使用中 badge', async () => {
  login(TENANT_OWNER)
  const { container } = renderApp('/dashboard')
  const ui = siderUI(container)
  await openGroup(ui, '概览', '仪表盘')
  expect(ui.getByText('我的渠道组')).toBeInTheDocument()
  expect(ui.queryByText('已开通')).not.toBeInTheDocument()
  expect(ui.queryByText('使用中')).not.toBeInTheDocument()
  expect(container.textContent || '').not.toContain('当前可买')
})

test('GWT-U15.3 tenant company admin /newapi is same 404 shell, no 抱歉', async () => {
  login(TENANT_COMPANY_ADMIN)
  renderApp('/newapi')
  expect(await screen.findByText('页面不存在或已被移除')).toBeInTheDocument()
  expect(await screen.findByRole('button', { name: /返回工作台/ })).toBeInTheDocument()
  expect(screen.queryByText(/抱歉/)).not.toBeInTheDocument()
  expect(screen.queryByText('AutoAgents')).not.toBeInTheDocument()
})

test('GWT-U25.3 tenant company admin /newapi is same 404 shell as missing page', async () => {
  login(TENANT_COMPANY_ADMIN)
  renderApp('/newapi')
  expect(await screen.findByText('页面不存在或已被移除')).toBeInTheDocument()
  expect(await screen.findByRole('button', { name: /返回工作台/ })).toBeInTheDocument()
  expect(screen.queryByText(/抱歉/)).not.toBeInTheDocument()
  expect(screen.queryByText('抱歉您没有权限')).not.toBeInTheDocument()
  expect(screen.queryByText('AutoAgents')).not.toBeInTheDocument()
  expect(screen.queryByText('还没有平台模型，去网关登记')).not.toBeInTheDocument()
  expect(screen.queryByText('LLM 网关管理面不可达，仅本地事件/探针')).not.toBeInTheDocument()
  expect(screen.queryByText('暂无渠道')).not.toBeInTheDocument()
  expect(screen.queryByRole('tab', { name: /总览/ })).not.toBeInTheDocument()
  expect(screen.queryByText('密钥')).not.toBeInTheDocument()
  expect(document.body.textContent || '').not.toContain('当前可买')
})

test('GWT-U15.3 tenant company admin listing sources is same 404 shell, no 抱歉', async () => {
  login(TENANT_COMPANY_ADMIN)
  renderApp('/capabilities/sources')
  expect(await screen.findByText('页面不存在或已被移除')).toBeInTheDocument()
  expect(await screen.findByRole('button', { name: /返回工作台/ })).toBeInTheDocument()
  expect(screen.queryByText(/抱歉/)).not.toBeInTheDocument()
  expect(screen.queryByText('AutoAgents')).not.toBeInTheDocument()
  expect(screen.queryByRole('tab', { name: '源' })).not.toBeInTheDocument()
  expect(screen.queryByText('还没有源。登记源后才能同步。')).not.toBeInTheDocument()
})

test('GWT-U15.3 tenant company admin /capabilities is shelf not 404', async () => {
  login(TENANT_COMPANY_ADMIN)
  renderApp('/capabilities')
  expect(await screen.findByTestId('tenant-shelf')).toBeInTheDocument()
  expect(screen.queryByText('页面不存在或已被移除')).not.toBeInTheDocument()
  expect(screen.queryByText(/抱歉/)).not.toBeInTheDocument()
  expect(screen.queryByRole('tab', { name: '源' })).not.toBeInTheDocument()
  expect(screen.queryByTestId('governance-shell')).not.toBeInTheDocument()
})
