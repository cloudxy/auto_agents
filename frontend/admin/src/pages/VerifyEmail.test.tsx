/** 决策 D21：邮箱验证落地页 */
import React from 'react'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import VerifyEmail from './VerifyEmail'
import { verifyEmail } from '../services/auth'
import { useAuthStore } from '../store/useAuthStore'

jest.mock('../services/auth', () => ({ verifyEmail: jest.fn(), login: jest.fn(), logoutSession: jest.fn() }))

const renderAt = (path: string) => render(<MemoryRouter initialEntries={[path]}><VerifyEmail /></MemoryRouter>)

beforeEach(() => {
  useAuthStore.setState({ token: 't', isAuthenticated: true, user: { access_token: 't', token_type: 'bearer', username: 'boss', is_admin: true, email_verify_pending: true } })
})

test('验证成功：显示成功并清掉待验证标记', async () => {
  ;(verifyEmail as jest.Mock).mockResolvedValue(undefined)
  renderAt('/verify-email?token=abc.def.ghi')
  expect(await screen.findByText('邮箱已验证')).toBeInTheDocument()
  expect(verifyEmail).toHaveBeenCalledWith('abc.def.ghi')
  expect(useAuthStore.getState().user?.email_verify_pending).toBe(false)
})

test('链接无效：给出可行动的说明', async () => {
  ;(verifyEmail as jest.Mock).mockRejectedValue({ response: { data: { message: '验证链接无效或已过期，请在后台重新发送。' } } })
  renderAt('/verify-email?token=bad')
  expect(await screen.findByText('没能完成验证')).toBeInTheDocument()
  expect(screen.getByText('验证链接无效或已过期，请在后台重新发送。')).toBeInTheDocument()
})

test('缺少 token 不发请求', async () => {
  ;(verifyEmail as jest.Mock).mockClear()
  renderAt('/verify-email')
  expect(await screen.findByText('没能完成验证')).toBeInTheDocument()
  expect(verifyEmail).not.toHaveBeenCalled()
})
