/**
 * 权限缓存生命周期回归（侧边栏缺失修复）：F5 后 persist 恢复登录态、
 * 模块缓存归零 → hook 挂载自动补拉 → 菜单经重渲染恢复。
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
  'menu:members', 'menu:usage', 'menu:platform-ops', 'menu:logs',
  'menu:llm', 'menu:newapi',
]

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

test('F5 后缓存空：挂载自动补拉，菜单恢复', async () => {
  // 模拟 persist 恢复登录态（token/user 存在），模块权限缓存为空
  useAuthStore.setState({
    token: 't', isAuthenticated: true,
    user: { username: 'admin', role: 'admin', is_admin: true } as never,
  })
  ;(api.get as jest.Mock).mockResolvedValue({ data: ADMIN_PERMS })

  render(<MemoryRouter><Probe /></MemoryRouter>)

  // 初始：缓存空 → 菜单全隐（安全侧）
  expect(screen.getByTestId('ready').textContent).toBe('false')

  // 补拉完成后：组结构与叶子恢复
  expect(await screen.findByText(/概览/)).toBeInTheDocument()
  await waitFor(() => expect(screen.getByTestId('ready').textContent).toBe('true'))
  expect(screen.getByText(/数据工厂/)).toBeInTheDocument()
  expect(screen.getByText(/系统管理/)).toBeInTheDocument()
  expect(api.get).toHaveBeenCalledWith('/auth/permissions')
})

test('未登录：不拉取，菜单保持全隐', async () => {
  clearCachedPermissions()  // 前一用例的模块级缓存不跨用例（被测设计）
  useAuthStore.setState({ token: null, isAuthenticated: false, user: null })
  const callCount = (api.get as jest.Mock).mock.calls.length
  render(<MemoryRouter><Probe /></MemoryRouter>)
  expect(screen.getByTestId('ready').textContent).toBe('false')
  expect((api.get as jest.Mock).mock.calls.length).toBe(callCount)  // 无新增请求
})

/**
 * bea13b5 回归：权限不可知（后端重启/网络瞬断 → refreshPermissions 失败 →
 * cachedPermissions=[]）时，filterMenu 返回全量菜单（仅保留 tenantOnly 过滤），
 * 侧边栏不再消失。修复前：缓存空 → 按空权限全滤光 → 菜单消失（复发链条）。
 */
test('补拉失败（后端不可达）：菜单全量兜底而非全滤光（bea13b5）', async () => {
  clearCachedPermissions()
  useAuthStore.setState({
    token: 't', isAuthenticated: true,
    user: { username: 'admin', role: 'admin', is_admin: true } as never,
  })
  ;(api.get as jest.Mock).mockRejectedValue(new Error('backend unreachable'))

  render(<MemoryRouter><Probe /></MemoryRouter>)

  // 补拉已尝试且失败（in-flight 结束，revision 已 bump）
  await waitFor(() => expect(api.get).toHaveBeenCalled())

  // 兜底断言：非 tenantOnly 组保留（全量菜单），而非全滤光
  expect(await screen.findByText(/概览/)).toBeInTheDocument()
  expect(screen.getByText(/数据工厂/)).toBeInTheDocument()
  expect(screen.getByText(/系统管理/)).toBeInTheDocument()
  // 权限仍未就绪（ready=false——兜底是显示语义，不是权限通过）
  expect(screen.getByTestId('ready').textContent).toBe('false')
})

/**
 * bea13b5 边界缺陷（T10 报，T12/F-T10-1 修复转正）：兜底分支此前只过滤
 * 顶层菜单的 tenantOnly，而 tenantOnly 标记实际全在叶子层（成员管理/用量
 * 看板）——后端不可达时纯平台超管（tenant_id=NULL）仍见 tenantOnly 菜单，
 * 点击 403。修复：filterTenantOnly 递归过滤（与权限分支同口径）。
 */
test('兜底分支同样过滤叶子层 tenantOnly（F-T10-1 修复转正）', async () => {
  clearCachedPermissions()
  useAuthStore.setState({
    token: 't', isAuthenticated: true,
    // 纯平台超管（tenant_id=NULL）
    user: { username: 'admin', role: 'admin', is_admin: true } as never,
  })
  ;(api.get as jest.Mock).mockRejectedValue(new Error('backend unreachable'))

  render(<MemoryRouter><Probe /></MemoryRouter>)
  await waitFor(() => expect(api.get).toHaveBeenCalled())
  await screen.findByText(/概览/)

  expect(screen.queryByText(/成员管理/)).not.toBeInTheDocument()
  expect(screen.queryByText(/用量看板/)).not.toBeInTheDocument()
})
