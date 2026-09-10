/**
 * T-03 后台登录：企业注册回链、from 回跳、开放重定向拒绝（GWT-04.3）。
 */
import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'

jest.mock('../services/auth', () => ({
  login: jest.fn(),
}))

jest.mock('../hooks/usePermission', () => ({
  refreshPermissions: jest.fn().mockResolvedValue(undefined),
  clearCachedPermissions: jest.fn(),
}))

import { login as apiLogin } from '../services/auth'
import { useAuthStore } from '../store/useAuthStore'
import Login from './Login'

const loginApi = apiLogin as jest.Mock

function Where() {
  const loc = useLocation()
  return <div data-testid="where">{loc.pathname}</div>
}

function renderLogin(initial = '/login') {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/dashboard" element={<Where />} />
        <Route path="/spiders/tasks" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  )
}

function fillAndSubmit() {
  fireEvent.change(screen.getByPlaceholderText('用户名'), { target: { value: 'boss' } })
  fireEvent.change(screen.getByPlaceholderText('密码'), { target: { value: 'SuperSecret1!' } })
  fireEvent.click(screen.getByRole('button', { name: /登\s*录/ }))
}

beforeEach(() => {
  loginApi.mockReset()
  localStorage.clear()
  useAuthStore.setState({
    token: null, user: null, isAuthenticated: false, rememberMe: false,
  })
  Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
})

test('GWT-04.3 footer has 没有账号？企业注册 back to official register', () => {
  renderLogin()
  expect(screen.getByText(/没有账号？/)).toBeInTheDocument()
  const link = screen.getByRole('link', { name: '企业注册' })
  expect(link).toHaveAttribute('href', 'http://localhost:9113/register')
})

test('GWT-04.1 login with from query returns to that in-site path', async () => {
  loginApi.mockResolvedValue({
    access_token: 't', token_type: 'bearer', username: 'boss', is_admin: true, role: 'admin',
  })
  renderLogin('/login?from=/spiders/tasks')
  fillAndSubmit()
  expect(await screen.findByTestId('where')).toHaveTextContent('/spiders/tasks')
})

test('open redirect from= is ignored', async () => {
  loginApi.mockResolvedValue({
    access_token: 't', token_type: 'bearer', username: 'boss', is_admin: true, role: 'admin',
  })
  renderLogin('/login?from=https://evil.example')
  fillAndSubmit()
  expect(await screen.findByTestId('where')).toHaveTextContent('/dashboard')
})

test('credential 401 uses 用户名或密码不正确 copy not expiry copy', async () => {
  loginApi.mockRejectedValue({
    response: {
      status: 401,
      data: { success: false, code: 'AUTH_FAILED', message: '用户名或密码错误' },
    },
  })
  renderLogin()
  fillAndSubmit()
  expect(await screen.findByRole('alert')).toHaveTextContent('用户名或密码不正确。核对后再登录。')
  expect(screen.queryByText(/企业已到期或停用/)).not.toBeInTheDocument()
  expect(screen.getByPlaceholderText('用户名')).toBeInTheDocument()
})

test('offline login keeps input and shows network copy', async () => {
  Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
  renderLogin()
  fillAndSubmit()
  expect(await screen.findByRole('alert')).toHaveTextContent('登录请求失败，检查网络后重试。')
  expect(loginApi).not.toHaveBeenCalled()
  expect((screen.getByPlaceholderText('用户名') as HTMLInputElement).value).toBe('boss')
})

test('safeInternalPath rejects protocol-relative and login loop', async () => {
  loginApi.mockResolvedValue({
    access_token: 't', token_type: 'bearer', username: 'boss', is_admin: true, role: 'admin',
  })
  renderLogin('/login?from=//evil.example')
  fillAndSubmit()
  expect(await screen.findByTestId('where')).toHaveTextContent('/dashboard')
})

test('sessionExpired state shows 登录已过期 copy', async () => {
  render(
    <MemoryRouter
      initialEntries={[{ pathname: '/login', search: '?from=/dashboard', state: { sessionExpired: true, from: '/dashboard' } }]}
    >
      <Routes>
        <Route path="/login" element={<Login />} />
      </Routes>
    </MemoryRouter>,
  )
  await waitFor(() => {
    expect(screen.getByText('登录已过期。重新登录后回到刚才的页面。')).toBeInTheDocument()
  })
})
