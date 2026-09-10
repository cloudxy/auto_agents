/**
 * 权限缓存 + 租户壳（T-05）：空缓存读叶；平台写叶仅 is_platform_admin。
 */
import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

jest.mock('../services/api', () => ({
  __esModule: true,
  default: { get: jest.fn() },
  unwrap: jest.fn(),
}))

import api from '../services/api'
import { clearCachedPermissions, usePermission } from './usePermission'
import { useAuthStore } from '../store/useAuthStore'

const ADMIN_PERMS = [
  'menu:dashboard', 'menu:spiders', 'menu:spiders.tasks', 'menu:spiders.logs',
  'menu:users', 'menu:data', 'menu:settings', 'menu:ai', 'menu:skills',
  'menu:spiders.nodes', 'menu:members', 'menu:usage', 'menu:platform-ops', 'menu:logs',
  'menu:llm', 'menu:newapi',
]

function labelsOf(root: HTMLElement): string {
  return root.textContent || ''
}

function Probe() {
  const { filteredMenus, permissionsReady } = usePermission()
  return (
    <div>
      <span data-testid="ready">{String(permissionsReady)}</span>
      <ul>
        {filteredMenus.map((g) => (
          <li key={g.key}>{g.label}：{(g.children || []).map((c) => c.label).join('/')}</li>
        ))}
      </ul>
    </div>
  )
}

const tenantAdmin = {
  username: 'boss', role: 'admin' as const, is_admin: true,
  is_platform_admin: false, tenant_id: 9,
}

beforeEach(() => {
  clearCachedPermissions()
  ;(api.get as jest.Mock).mockReset()
})

test('F5 后缓存空：挂载自动补拉，菜单恢复', async () => {
  useAuthStore.setState({
    token: 't', isAuthenticated: true,
    user: { ...tenantAdmin } as never,
  })
  ;(api.get as jest.Mock).mockResolvedValue({ data: ADMIN_PERMS })

  render(<MemoryRouter><Probe /></MemoryRouter>)

  expect(screen.getByTestId('ready').textContent).toBe('false')

  expect(await screen.findByText(/概览/)).toBeInTheDocument()
  await waitFor(() => expect(screen.getByTestId('ready').textContent).toBe('true'))
  expect(screen.getByText(/数据工厂/)).toBeInTheDocument()
  expect(screen.getByText(/系统管理/)).toBeInTheDocument()
  expect(api.get).toHaveBeenCalledWith('/auth/permissions')
})

test('未登录：不拉取，菜单保持全隐', async () => {
  clearCachedPermissions()
  useAuthStore.setState({ token: null, isAuthenticated: false, user: null })
  const callCount = (api.get as jest.Mock).mock.calls.length
  render(<MemoryRouter><Probe /></MemoryRouter>)
  expect(screen.getByTestId('ready').textContent).toBe('false')
  expect((api.get as jest.Mock).mock.calls.length).toBe(callCount)
})

test('空缓存/补拉失败：读叶保留，不得露出平台写叶（GWT-17.2）', async () => {
  useAuthStore.setState({
    token: 't', isAuthenticated: true,
    user: { ...tenantAdmin } as never,
  })
  ;(api.get as jest.Mock).mockRejectedValue(new Error('backend unreachable'))

  const { container } = render(<MemoryRouter><Probe /></MemoryRouter>)
  await waitFor(() => expect(api.get).toHaveBeenCalled())
  expect(await screen.findByText(/概览/)).toBeInTheDocument()
  expect(screen.getByText(/数据工厂/)).toBeInTheDocument()
  expect(screen.getByText(/系统管理/)).toBeInTheDocument()
  expect(screen.getByTestId('ready').textContent).toBe('false')
  const text = labelsOf(container)
  expect(text).not.toMatch(/中转站管控/)
  expect(text).not.toMatch(/平台运营台/)
  expect(text).not.toMatch(/用户管理/)
})

test('兜底分支同样过滤叶子层 tenantOnly（F-T10-1）', async () => {
  useAuthStore.setState({
    token: 't', isAuthenticated: true,
    user: { username: 'root', role: 'admin', is_admin: true, is_platform_admin: true } as never,
  })
  ;(api.get as jest.Mock).mockRejectedValue(new Error('backend unreachable'))

  render(<MemoryRouter><Probe /></MemoryRouter>)
  await waitFor(() => expect(api.get).toHaveBeenCalled())
  await screen.findByText(/概览/)

  expect(screen.queryByText(/成员管理/)).not.toBeInTheDocument()
  expect(screen.queryByText(/用量看板/)).not.toBeInTheDocument()
  expect(screen.queryByText(/我的安装/)).not.toBeInTheDocument()
})

test('租户公司管理员权限已加载：有仪表盘/数据工厂，无中转写/运营/用户管理（GWT-07.2/17.1）', async () => {
  useAuthStore.setState({
    token: 't', isAuthenticated: true,
    user: { ...tenantAdmin } as never,
  })
  ;(api.get as jest.Mock).mockResolvedValue({ data: ADMIN_PERMS })

  const { container } = render(<MemoryRouter><Probe /></MemoryRouter>)
  await waitFor(() => expect(screen.getByTestId('ready').textContent).toBe('true'))
  expect(screen.getByText(/仪表盘/)).toBeInTheDocument()
  expect(screen.getByText(/数据工厂/)).toBeInTheDocument()
  expect(screen.getByText(/LLM 配置/)).toBeInTheDocument()
  expect(screen.getByText(/我的安装/)).toBeInTheDocument()
  const text = labelsOf(container)
  expect(text).not.toMatch(/中转站管控/)
  expect(text).not.toMatch(/平台运营台/)
  expect(text).not.toMatch(/用户管理/)
  expect(text).not.toMatch(/产品事实/)
  expect(text).not.toMatch(/分析入口/)
  expect(text).not.toMatch(/市场分析/)
})

test('平台超管权限已加载：中转站管控可见（GWT-07.1）', async () => {
  useAuthStore.setState({
    token: 't', isAuthenticated: true,
    user: { username: 'root', role: 'admin', is_admin: true, is_platform_admin: true } as never,
  })
  ;(api.get as jest.Mock).mockResolvedValue({ data: ADMIN_PERMS })

  render(<MemoryRouter><Probe /></MemoryRouter>)
  await waitFor(() => expect(screen.getByTestId('ready').textContent).toBe('true'))
  expect(screen.getByText(/中转站管控/)).toBeInTheDocument()
  expect(screen.getByText(/平台运营台/)).toBeInTheDocument()
})
