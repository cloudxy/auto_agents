/**
 * T-21 后台定价：专业/企业「去结账」；买方进结账；经办联系管理员；无免费注册。
 */
import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useSearchParams } from 'react-router-dom'

import Pricing from './Pricing'
import { CHECKOUT_PATH_ENTERPRISE, CHECKOUT_PATH_PRO, CONTACT_ADMIN_COPY } from '../constants/collectCopy'
import { withQuery } from '../testUtils'
import { listPlans } from '../services/billing'

jest.mock('../services/billing', () => ({
  listPlans: jest.fn(),
  fetchPublicContact: jest.fn().mockRejectedValue(new Error('offline')),
}))

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
  return render(withQuery(
    <MemoryRouter initialEntries={['/pricing']}>
      <Routes>
        <Route path="/pricing" element={<Pricing />} />
        <Route path="/billing/checkout" element={<CheckoutProbe />} />
        <Route path="/register" element={<div>register-probe</div>} />
      </Routes>
    </MemoryRouter>,
  ))
}

beforeEach(() => {
  mockUserState.current = { tenant_id: 1, tenant_role: 'owner', is_platform_admin: false }
  ;(listPlans as jest.Mock).mockReset().mockResolvedValue([
    { id: 1, slug: 'free', name: '免费档', price_cents: 0, period: 'month' },
    { id: 2, slug: 'pro', name: '专业档', price_cents: 39900, period: 'month' },
    { id: 3, slug: 'enterprise', name: '企业档', price_cents: 1299000, period: 'year' },
  ])
})

test('审计 F1-1：后台定价的价格读 /billing/plans，不再手抄（原先写死 ¥299/月 与「定制」）', async () => {
  renderPricing()
  expect(await screen.findByText('¥399/月')).toBeInTheDocument()
  expect(screen.getByText('¥12,990/年')).toBeInTheDocument()
  expect(screen.queryByText('定制')).toBeNull()
})

test('价目读取失败：付费档提示以结账页为准，购买入口不受影响', async () => {
  ;(listPlans as jest.Mock).mockRejectedValue(new Error('network'))
  renderPricing()
  expect((await screen.findAllByText('价格以结账页为准')).length).toBe(2)
  expect(screen.getAllByRole('button', { name: '去结账' })).toHaveLength(1)  // 企业档 D17 走联系我们
})

test('GWT-U35.1 buyer 专业档 去结账 product=plan_pro, not register', () => {
  renderPricing()
  const buttons = screen.getAllByRole('button', { name: '去结账' })
  expect(buttons).toHaveLength(1)
  fireEvent.click(buttons[0])
  expect(screen.getByTestId('checkout-probe')).toHaveTextContent('plan_pro')
  expect(screen.queryByText('register-probe')).toBeNull()
  expect(screen.queryByRole('link', { name: /免费注册/ })).toBeNull()
  expect(document.body.textContent).not.toContain('当前可买')
  expect(document.body.textContent).not.toContain('支付已通')
  expect(document.body.textContent).not.toContain('预告不可购买')
})

test('D17：企业档按需定制，走「联系我们」（带邮箱与响应时效），不自助结账；D32 撤下私有技能库', async () => {
  const { fetchPublicContact } = jest.requireMock('../services/billing')
  ;(fetchPublicContact as jest.Mock).mockResolvedValueOnce({
    duty_contact: '', contact_email: 'sales@example.com', contact_sla: '工作日 24 小时内回复',
  })
  ;(listPlans as jest.Mock).mockResolvedValue([
    { id: 2, slug: 'pro', name: '专业档', price_cents: 39900, period: 'month' },
    { id: 3, slug: 'enterprise', name: '企业档', price_cents: 99900, period: 'month', sales_led: true },
  ])
  renderPricing()
  expect(await screen.findByText('按需定制')).toBeInTheDocument()
  const contact = await screen.findByRole('link', { name: '联系我们' })
  expect(contact.getAttribute('href')).toContain('mailto:sales@example.com')
  expect(screen.getByText('sales@example.com · 工作日 24 小时内回复')).toBeInTheDocument()
  expect(screen.queryByTestId('checkout-probe')).toBeNull()
  expect(document.body.textContent).not.toContain('私有技能库')
  expect(CHECKOUT_PATH_PRO).toContain('plan_pro')
})

test('GWT-U35.3 operator 去结账 is contact admin, no order path', () => {
  mockUserState.current = { tenant_id: 1, tenant_role: 'operator', is_platform_admin: false }
  renderPricing()
  fireEvent.click(screen.getAllByRole('button', { name: '去结账' })[0])
  expect(screen.getByText(CONTACT_ADMIN_COPY)).toBeInTheDocument()
  expect(screen.queryByTestId('checkout-probe')).toBeNull()
  expect(screen.getAllByRole('button', { name: '去结账' })).toHaveLength(1)
})
