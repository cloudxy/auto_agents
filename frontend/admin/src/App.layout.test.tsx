/**
 * T-29 / FR-96（ADR-0022 单布局树）组件测试：
 * - GWT-96.1 跨组切换：超管点另一组菜单项，AdminLayout 侧栏实例不重挂
 *   （同一 DOM 节点引用）、既有展开状态保持、不出现「权限加载中」。
 * - GWT-96.2 组内切换：同组切叶，侧栏实例与展开状态不变。
 * - 404 同形回归：非超管（含未登录）直打平台写面 = 缺页同形 404，
 *   不挂侧栏、不进登录重定向（原 PlatformAdminLayout 语义，GWT-96.4 不变式）。
 *
 * 注：菜单叶文案会与页头/页面卡片同名（pageTitleFor 派生），
 * 侧栏查询一律 within(sider) 限定；页头标题取 .ant-layout-header 首个 div。
 */
import React from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import { useAuthStore } from './store/useAuthStore'

jest.mock('./services/menus', () => ({
  fetchDynamicMenus: jest.fn().mockResolvedValue([]),
}))

// 权限快照走 /auth/permissions（成功信封）；其余端点一律拒绝——
// 页面级请求都有 catch / react-query 兜底，拒绝路径不产生未处理 Promise。
jest.mock('./services/api', () => {
  const envelope = (data: unknown) => ({ success: true, code: 'OK', message: 'ok', data })
  return {
    __esModule: true,
    default: {
      get: jest.fn((url: string) =>
        url === '/auth/permissions'
          ? Promise.resolve(envelope([
            'menu:dashboard', 'menu:spiders.tasks', 'menu:spiders.logs', 'menu:users',
          ]))
          : Promise.reject(new Error('mock network'))),
      post: jest.fn(() => Promise.reject(new Error('mock network'))),
      put: jest.fn(() => Promise.reject(new Error('mock network'))),
      patch: jest.fn(() => Promise.reject(new Error('mock network'))),
      delete: jest.fn(() => Promise.reject(new Error('mock network'))),
    },
  }
})

const PLATFORM_SUPER_ADMIN = {
  access_token: 't', token_type: 'bearer', username: 'root',
  is_admin: true, role: 'admin', is_platform_admin: true, tenant_id: null,
}

const TENANT_COMPANY_ADMIN = {
  access_token: 't', token_type: 'bearer', username: 'boss',
  is_admin: true, role: 'admin', is_platform_admin: false, tenant_id: 3,
}

beforeEach(() => {
  useAuthStore.setState({
    token: null, user: null, isAuthenticated: false, rememberMe: false,
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

/** 侧栏 DOM 节点引用：重挂会换新节点，不重挂则同一引用 */
const siderNode = (container: HTMLElement) => container.querySelector('.ant-layout-sider')

/** 限定在侧栏内的查询句柄 */
const siderUI = (container: HTMLElement) => within(siderNode(container) as HTMLElement)

/** 页头标题（pageTitleFor 派生，header 首个 div；不含右侧欢迎语） */
const headerTitle = () =>
  (document.querySelector('.ant-layout-header > div') as HTMLElement | null)?.textContent || ''

/** 展开侧栏分组并等权限就绪（授予的叶子在侧栏出现 = loadState==='loaded'） */
const expandGroupAndWaitReady = async (
  ui: ReturnType<typeof within>, group: string, grantedLeaf: string,
) => {
  fireEvent.click(ui.getByText(group))
  await ui.findByText(grantedLeaf)
  expect(ui.getByText(group).closest('.ant-menu-submenu')).toHaveClass('ant-menu-submenu-open')
}

test('GWT-96.1 cross-group menu click keeps the same sider instance and expansion', async () => {
  useAuthStore.setState({
    token: 't', isAuthenticated: true, rememberMe: false, user: PLATFORM_SUPER_ADMIN,
  })
  const { container } = renderApp('/dashboard')
  const ui = siderUI(container)

  await expandGroupAndWaitReady(ui, '概览', '仪表盘')
  await expandGroupAndWaitReady(ui, '数据工厂', '采集任务')
  fireEvent.click(ui.getByText('系统管理'))
  await ui.findByText('用户管理')

  const siderBefore = siderNode(container)
  expect(siderBefore).not.toBeNull()

  // 跨组切换：概览组（仪表盘，当前页）→ 系统管理组（用户管理）
  fireEvent.click(ui.getByText('用户管理'))

  await waitFor(() => expect(window.location.pathname).toBe('/users'))
  await waitFor(() => expect(headerTitle()).toBe('用户管理'))

  // 侧栏同一 DOM 节点（未重挂）+ 既有展开状态保持 + 不闪「权限加载中」
  expect(siderNode(container)).toBe(siderBefore)
  expect(ui.getByText('采集任务')).toBeInTheDocument()
  expect(ui.getByText('数据工厂').closest('.ant-menu-submenu')).toHaveClass('ant-menu-submenu-open')
  expect(screen.queryByText('权限加载中')).not.toBeInTheDocument()
})

test('GWT-96.2 in-group leaf switch keeps the same sider instance and expansion', async () => {
  useAuthStore.setState({
    token: 't', isAuthenticated: true, rememberMe: false, user: PLATFORM_SUPER_ADMIN,
  })
  const { container } = renderApp('/spiders/tasks')
  const ui = siderUI(container)

  await expandGroupAndWaitReady(ui, '数据工厂', '采集任务')

  const siderBefore = siderNode(container)
  expect(siderBefore).not.toBeNull()

  // 组内切换：采集任务 → 运行日志（同在数据工厂组）
  fireEvent.click(ui.getByText('运行日志'))

  await waitFor(() => expect(window.location.pathname).toBe('/spiders/logs'))
  await waitFor(() => expect(headerTitle()).toBe('运行日志'))

  expect(siderNode(container)).toBe(siderBefore)
  expect(ui.getByText('采集任务')).toBeInTheDocument()
  expect(ui.getByText('数据工厂').closest('.ant-menu-submenu')).toHaveClass('ant-menu-submenu-open')
  expect(screen.queryByText('权限加载中')).not.toBeInTheDocument()
})

test('tenant company admin direct hit on merged /users is same 404 shell without sidebar', async () => {
  useAuthStore.setState({
    token: 't', isAuthenticated: true, rememberMe: false, user: TENANT_COMPANY_ADMIN,
  })
  renderApp('/users')

  expect(await screen.findByText('页面不存在或已被移除')).toBeInTheDocument()
  expect(await screen.findByRole('button', { name: /返回工作台/ })).toBeInTheDocument()
  expect(screen.queryByText('AutoAgents')).not.toBeInTheDocument()
  expect(screen.queryByText('权限加载中')).not.toBeInTheDocument()
})

test('unauthenticated direct hit on merged /newapi stays 404 shell, no login redirect', async () => {
  renderApp('/newapi')

  expect(await screen.findByText('页面不存在或已被移除')).toBeInTheDocument()
  expect(window.location.pathname).toBe('/newapi')
  expect(screen.queryByPlaceholderText('用户名')).not.toBeInTheDocument()
})

// T-11 / GWT-61.3：租户无 /newapi 入口——已登录租户直打 = 缺页同形 404（守卫 T-29 已落，此处验收断言）
test('GWT-61.3 authenticated tenant direct hit on /newapi is the same missing-page 404 shell', async () => {
  useAuthStore.setState({
    token: 't', isAuthenticated: true, rememberMe: false, user: TENANT_COMPANY_ADMIN,
  })
  const { container } = renderApp('/newapi')

  expect(await screen.findByText('页面不存在或已被移除')).toBeInTheDocument()
  expect(await screen.findByRole('button', { name: /返回工作台/ })).toBeInTheDocument()
  // 同形：不挂侧栏、不出现值班页内容或权限中转/登录重定向
  expect(container.querySelector('.ant-layout-sider')).toBeNull()
  expect(screen.queryByText('中转站管控')).not.toBeInTheDocument()
  expect(screen.queryByText('权限加载中')).not.toBeInTheDocument()
  expect(screen.queryByPlaceholderText('用户名')).not.toBeInTheDocument()
})
