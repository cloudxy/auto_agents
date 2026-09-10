/**
 * T-05：平台写面直打 404 同形；/llm 对租户 admin 不整页 404。
 */
import React from 'react'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import ProtectedRoute from './ProtectedRoute'
import { useAuthStore } from '../store/useAuthStore'

jest.mock('../pages/NotFound', () => ({
  __esModule: true,
  default: () => (
    <div>
      <div>页面不存在或已被移除</div>
      <button type="button">返回工作台</button>
    </div>
  ),
}))

beforeEach(() => {
  useAuthStore.setState({
    token: 't', isAuthenticated: true, rememberMe: false,
    user: {
      access_token: 't', token_type: 'bearer', username: 'boss',
      is_admin: true, role: 'admin', is_platform_admin: false, tenant_id: 3,
    },
  })
})

test('tenant company admin hitting platform route sees NotFound not 抱歉', () => {
  render(
    <MemoryRouter initialEntries={['/newapi']}>
      <Routes>
        <Route
          path="/newapi"
          element={(
            <ProtectedRoute requirePlatformAdmin>
              <div>渠道列表</div>
            </ProtectedRoute>
          )}
        />
      </Routes>
    </MemoryRouter>,
  )
  expect(screen.getByText('页面不存在或已被移除')).toBeInTheDocument()
  expect(screen.getByText('返回工作台')).toBeInTheDocument()
  expect(screen.queryByText('渠道列表')).not.toBeInTheDocument()
  expect(screen.queryByText(/抱歉/)).not.toBeInTheDocument()
})

test('tenant company admin can open /llm (not whole-page 404)', () => {
  render(
    <MemoryRouter initialEntries={['/llm']}>
      <Routes>
        <Route
          path="/llm"
          element={(
            <ProtectedRoute>
              <div>本企业供应商</div>
            </ProtectedRoute>
          )}
        />
      </Routes>
    </MemoryRouter>,
  )
  expect(screen.getByText('本企业供应商')).toBeInTheDocument()
  expect(screen.queryByText('页面不存在或已被移除')).not.toBeInTheDocument()
})

test('operator can open /llm without requireAdmin (GWT-73.4 enter)', () => {
  useAuthStore.setState({
    token: 't', isAuthenticated: true, rememberMe: false,
    user: {
      access_token: 't', token_type: 'bearer', username: 'op',
      is_admin: false, role: 'operator', is_platform_admin: false, tenant_id: 3,
    },
  })
  render(
    <MemoryRouter initialEntries={['/llm']}>
      <Routes>
        <Route path="/unauthorized" element={<div>无权限</div>} />
        <Route
          path="/llm"
          element={(
            <ProtectedRoute>
              <div>本企业供应商</div>
            </ProtectedRoute>
          )}
        />
      </Routes>
    </MemoryRouter>,
  )
  expect(screen.getByText('本企业供应商')).toBeInTheDocument()
  expect(screen.queryByText('无权限')).not.toBeInTheDocument()
  expect(screen.queryByText('页面不存在或已被移除')).not.toBeInTheDocument()
})

test('unauthenticated platform route is NotFound not login', () => {
  useAuthStore.setState({ token: null, isAuthenticated: false, user: null })
  render(
    <MemoryRouter initialEntries={['/newapi']}>
      <Routes>
        <Route path="/login" element={<div>登录页</div>} />
        <Route
          path="/newapi"
          element={(
            <ProtectedRoute requirePlatformAdmin>
              <div>渠道列表</div>
            </ProtectedRoute>
          )}
        />
      </Routes>
    </MemoryRouter>,
  )
  expect(screen.getByText('页面不存在或已被移除')).toBeInTheDocument()
  expect(screen.queryByText('登录页')).not.toBeInTheDocument()
  expect(screen.queryByText('渠道列表')).not.toBeInTheDocument()
})
