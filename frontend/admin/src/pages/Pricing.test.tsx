/**
 * T-21 后台定价：专业/企业「去结账」；买方进结账；经办联系管理员；无免费注册。
 */
import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useSearchParams } from 'react-router-dom'

import Pricing from './Pricing'
import { CHECKOUT_PATH_ENTERPRISE, CHECKOUT_PATH_PRO, CONTACT_ADMIN_COPY } from '../constants/collectCopy'

const mockUserState: { current: Record<string, unknown> | null } = { current: null }

jest.mock('../store/useAuthStore', () => ({
  useAuthStore: (sel: (s: { user: Record<string, unknown> | null }) => unknown) =>
    sel({ user: mockUserState.current }),
}))

function CheckoutProbe() {
  const [params] = useSearchParams()
  return <div data-testid="checkout-probe">{params.get('product')}</div>
}

function renderPricing() {
  return render(
    <MemoryRouter initialEntries={['/pricing']}>
      <Routes>
        <Route path="/pricing" element={<Pricing />} />
        <Route path="/billing/checkout" element={<CheckoutProbe />} />
        <Route path="/register" element={<div>register-probe</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  mockUserState.current = { tenant_id: 1, tenant_role: 'owner', is_platform_admin: false }
})

test('GWT-U35.1 buyer 专业档 去结账 product=plan_pro, not register', () => {
  renderPricing()
  const buttons = screen.getAllByRole('button', { name: '去结账' })
  expect(buttons).toHaveLength(2)
  fireEvent.click(buttons[0])
  expect(screen.getByTestId('checkout-probe')).toHaveTextContent('plan_pro')
  expect(screen.queryByText('register-probe')).toBeNull()
  expect(screen.queryByRole('link', { name: /免费注册/ })).toBeNull()
  expect(document.body.textContent).not.toContain('当前可买')
  expect(document.body.textContent).not.toContain('预告不可购买')
})

test('GWT-U35.5 buyer 企业档 去结账 product=plan_enterprise', () => {
  renderPricing()
  fireEvent.click(screen.getAllByRole('button', { name: '去结账' })[1])
  expect(screen.getByTestId('checkout-probe')).toHaveTextContent('plan_enterprise')
  expect(CHECKOUT_PATH_PRO).toContain('plan_pro')
  expect(CHECKOUT_PATH_ENTERPRISE).toContain('plan_enterprise')
})

test('GWT-U35.3 operator 去结账 is contact admin, no order path', () => {
  mockUserState.current = { tenant_id: 1, tenant_role: 'operator', is_platform_admin: false }
  renderPricing()
  fireEvent.click(screen.getAllByRole('button', { name: '去结账' })[0])
  expect(screen.getByText(CONTACT_ADMIN_COPY)).toBeInTheDocument()
  expect(screen.queryByTestId('checkout-probe')).toBeNull()
  expect(screen.getAllByRole('button', { name: '去结账' })).toHaveLength(2)
})
