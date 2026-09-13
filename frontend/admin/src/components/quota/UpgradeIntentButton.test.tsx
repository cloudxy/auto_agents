/**
 * T-04 / GWT-U02.6·U02.7：申请提升分角色着陆。不建单。
 */
import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useSearchParams } from 'react-router-dom'

jest.mock('../../services/usage', () => ({
  fetchUpgradeIntent: jest.fn(),
}))

jest.mock('../../services/billing', () => ({
  createOrder: jest.fn(),
}))

import { UpgradeIntentButton } from './UpgradeIntentButton'
import { fetchUpgradeIntent } from '../../services/usage'
import { createOrder } from '../../services/billing'
import {
  CHECKOUT_PATH_PRO,
  CONTACT_ADMIN_COPY,
  CONTACT_ADMIN_DETAIL,
  UPGRADE_CTA,
} from '../../constants/collectCopy'

function CheckoutProbe() {
  const [params] = useSearchParams()
  return <div data-testid="checkout-probe">{params.get('product')}</div>
}

function renderBtn() {
  return render(
    <MemoryRouter initialEntries={['/usage']}>
      <Routes>
        <Route path="/usage" element={<UpgradeIntentButton />} />
        <Route path="/billing/checkout" element={<CheckoutProbe />} />
        <Route path="/register" element={<div>register-probe</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  ;(fetchUpgradeIntent as jest.Mock).mockReset()
  ;(createOrder as jest.Mock).mockReset()
})

test('GWT-U02.6 operator upgrade-intent opens contact-admin, no checkout no order', async () => {
  ;(fetchUpgradeIntent as jest.Mock).mockResolvedValueOnce({
    action: 'contact_admin',
    product: 'plan_pro',
    checkout_path: null,
    message: CONTACT_ADMIN_COPY,
  })
  renderBtn()
  fireEvent.click(screen.getByRole('button', { name: UPGRADE_CTA }))
  expect(await screen.findByText(CONTACT_ADMIN_COPY)).toBeInTheDocument()
  expect(screen.getByText(CONTACT_ADMIN_DETAIL)).toBeInTheDocument()
  expect(screen.queryByTestId('checkout-probe')).toBeNull()
  expect(screen.queryByText('register-probe')).toBeNull()
  expect(createOrder).not.toHaveBeenCalled()
  expect(document.body.textContent).not.toContain('当前可买')
  expect(document.body.textContent).not.toContain('申请提升配额')
})

test('GWT-U02.6 viewer upgrade-intent is contact-admin, not checkout', async () => {
  ;(fetchUpgradeIntent as jest.Mock).mockResolvedValueOnce({
    action: 'contact_admin',
    product: 'plan_pro',
    checkout_path: null,
    message: CONTACT_ADMIN_COPY,
  })
  renderBtn()
  fireEvent.click(screen.getByRole('button', { name: UPGRADE_CTA }))
  expect(await screen.findByRole('button', { name: '知道了' })).toBeInTheDocument()
  expect(screen.queryByTestId('checkout-probe')).toBeNull()
  expect(createOrder).not.toHaveBeenCalled()
})

test('GWT-U02.7 buyer upgrade-intent goes to checkout product=plan_pro, no order', async () => {
  ;(fetchUpgradeIntent as jest.Mock).mockResolvedValueOnce({
    action: 'checkout',
    product: 'plan_pro',
    checkout_path: CHECKOUT_PATH_PRO,
    message: '去结账',
  })
  renderBtn()
  fireEvent.click(screen.getByRole('button', { name: UPGRADE_CTA }))
  expect(await screen.findByTestId('checkout-probe')).toHaveTextContent('plan_pro')
  expect(screen.queryByText(CONTACT_ADMIN_COPY)).toBeNull()
  expect(createOrder).not.toHaveBeenCalled()
  expect(fetchUpgradeIntent).toHaveBeenCalledWith('plan_pro')
})

test('button copy is 申请提升 not 申请提升配额', () => {
  ;(fetchUpgradeIntent as jest.Mock).mockResolvedValue({
    action: 'contact_admin', product: 'plan_pro', checkout_path: null, message: CONTACT_ADMIN_COPY,
  })
  renderBtn()
  expect(screen.getByRole('button', { name: UPGRADE_CTA })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '申请提升配额' })).toBeNull()
  expect(screen.queryByRole('button', { name: '提交升级申请' })).toBeNull()
})
