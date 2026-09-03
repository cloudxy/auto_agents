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
