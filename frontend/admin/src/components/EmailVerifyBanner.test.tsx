/** 决策 D21：待验证邮箱提示——负责人可重发，成员提示找负责人，已验证不显示 */
import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import EmailVerifyBanner from './EmailVerifyBanner'
import { resendVerification } from '../services/auth'
import { useAuthStore } from '../store/useAuthStore'

jest.mock('../services/auth', () => ({ resendVerification: jest.fn().mockResolvedValue(undefined), login: jest.fn(), logoutSession: jest.fn() }))

const asUser = (over: Record<string, unknown>) =>
  useAuthStore.setState({ user: { access_token: 't', token_type: 'bearer', username: 'u', is_admin: true, ...over } })

test('负责人待验证：提示 + 重新发送', async () => {
  asUser({ tenant_role: 'owner', email_verify_pending: true })
  render(<EmailVerifyBanner />)
  expect(screen.getByText('验证注册邮箱后才能使用 AI 规划')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /重新发送/ }))
  await waitFor(() => expect(resendVerification).toHaveBeenCalledTimes(1))
})

test('成员：提示找负责人，没有重发按钮', () => {
  asUser({ tenant_role: 'operator', email_verify_pending: true })
  render(<EmailVerifyBanner />)
  expect(screen.getByText('企业负责人验证注册邮箱后才能使用 AI 规划')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /重新发送/ })).toBeNull()
})

test('已验证：不显示', () => {
  asUser({ tenant_role: 'owner', email_verify_pending: false })
  const { container } = render(<EmailVerifyBanner />)
  expect(container).toBeEmptyDOMElement()
})
