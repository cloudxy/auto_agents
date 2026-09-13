/**
 * T-19 结账：支付宝/微信选择；未配空态；待支付 / 开通处理中；买方 POST；经办联系管理员。
 */
import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

jest.mock('../services/billing', () => ({
  previewCheckout: jest.fn(),
  createCheckout: jest.fn(),
  createOrder: jest.fn(),
  listMyOrders: jest.fn(),
}))

import Checkout from './Checkout'
import { createCheckout, createOrder, listMyOrders, previewCheckout } from '../services/billing'
import {
  CHANNEL_ALIPAY,
  CHANNEL_UNCONFIGURED_COPY,
  CHANNEL_WECHAT,
  CHECKOUT_CONTINUE_PAY,
  CHECKOUT_EMPTY_COPY,
  CHECKOUT_GO_PAY,
  CHECKOUT_PAID_PENDING_COPY,
  CHECKOUT_PENDING_COPY,
  CHECKOUT_PENDING_EXISTS_COPY,
  CHECKOUT_UNKNOWN_PRODUCT,
  CONTACT_ADMIN_COPY,
} from '../constants/collectCopy'

const BOTH_ON = [
  { channel: 'alipay', configured: true, selectable: true },
  { channel: 'wechat', configured: true, selectable: true },
]
const ONLY_ALIPAY = [
  { channel: 'alipay', configured: true, selectable: true },
  { channel: 'wechat', configured: false, selectable: false },
]
const NONE = [
  { channel: 'alipay', configured: false, selectable: false },
  { channel: 'wechat', configured: false, selectable: false },
]

function renderCheckout(path = '/billing/checkout?product=plan_pro') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/billing/checkout" element={<Checkout />} />
          <Route path="/register" element={<div>register-probe</div>} />
          <Route path="/pricing" element={<div>pricing-probe</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  ;(previewCheckout as jest.Mock).mockReset()
  ;(createCheckout as jest.Mock).mockReset()
  ;(createOrder as jest.Mock).mockReset()
  ;(listMyOrders as jest.Mock).mockReset()
  ;(listMyOrders as jest.Mock).mockResolvedValue([])
})

test('GWT-U32.2 both channels unconfigured: 收款通道未开通, no 去支付, no POST', async () => {
  ;(previewCheckout as jest.Mock).mockResolvedValueOnce({
    product: 'plan_pro',
    channels: NONE,
    empty_state: CHECKOUT_EMPTY_COPY,
    can_pay: false,
    order_id: null,
  })
  renderCheckout()
  expect(await screen.findByText(CHECKOUT_EMPTY_COPY)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: CHECKOUT_GO_PAY })).toBeNull()
  expect(screen.queryByRole('radio', { name: new RegExp(CHANNEL_ALIPAY) })).toBeNull()
  expect(document.body.textContent).not.toContain('当前可买')
  expect(document.body.textContent).not.toContain('Alipay SDK')
  expect(createCheckout).not.toHaveBeenCalled()
  expect(createOrder).not.toHaveBeenCalled()
  expect(previewCheckout).toHaveBeenCalledWith('plan_pro')
})

test('GWT-U30.1 buyer selects 支付宝 and POST checkout, not wechat, not register', async () => {
  ;(previewCheckout as jest.Mock).mockResolvedValue({
    product: 'plan_pro', channels: BOTH_ON, empty_state: null, can_pay: true, order_id: null, amount_cents: 29900,
  })
  ;(createCheckout as jest.Mock).mockResolvedValue({
    id: 11, status: 'checkout_pending', channel: 'alipay', product_code: 'plan_pro', amount_cents: 29900,
  })
  renderCheckout()
  expect(await screen.findByText(CHANNEL_ALIPAY)).toBeInTheDocument()
  expect(screen.getByText(CHANNEL_WECHAT)).toBeInTheDocument()
  fireEvent.click(screen.getByTestId('channel-alipay'))
  fireEvent.click(screen.getByRole('button', { name: CHECKOUT_GO_PAY }))
  await waitFor(() => expect(createCheckout).toHaveBeenCalledWith({ product: 'plan_pro', channel: 'alipay' }))
  expect(createCheckout).not.toHaveBeenCalledWith(expect.objectContaining({ channel: 'wechat' }))
  expect(createOrder).not.toHaveBeenCalled()
  expect(screen.queryByText('register-probe')).toBeNull()
})

test('GWT-U30.4 buyer selects 微信支付 and POST checkout, not alipay', async () => {
  ;(previewCheckout as jest.Mock).mockResolvedValue({
    product: 'plan_enterprise', channels: BOTH_ON, empty_state: null, can_pay: true, order_id: null,
  })
  ;(createCheckout as jest.Mock).mockResolvedValue({
    id: 12, status: 'checkout_pending', channel: 'wechat', product_code: 'plan_enterprise', amount_cents: 0,
  })
  renderCheckout('/billing/checkout?product=plan_enterprise')
  await screen.findByTestId('channel-wechat')
  fireEvent.click(screen.getByTestId('channel-wechat'))
  fireEvent.click(screen.getByRole('button', { name: CHECKOUT_GO_PAY }))
  await waitFor(() => expect(createCheckout).toHaveBeenCalledWith({
    product: 'plan_enterprise', channel: 'wechat',
  }))
  expect(createCheckout).not.toHaveBeenCalledWith(expect.objectContaining({ channel: 'alipay' }))
  expect(previewCheckout).toHaveBeenCalledWith('plan_enterprise')
})

test('GWT-U30.2 POST 409 shows 已有未完成的支付 and does not create a second order', async () => {
  ;(previewCheckout as jest.Mock).mockResolvedValue({
    product: 'plan_pro', channels: BOTH_ON, empty_state: null, can_pay: true, order_id: null,
  })
  ;(createCheckout as jest.Mock).mockRejectedValue({
    response: { status: 409, data: { code: 'CHECKOUT_PENDING_EXISTS', message: CHECKOUT_PENDING_EXISTS_COPY } },
  })
  renderCheckout()
  fireEvent.click(await screen.findByRole('button', { name: CHECKOUT_GO_PAY }))
  expect(await screen.findByText(CHECKOUT_PENDING_EXISTS_COPY)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: CHECKOUT_CONTINUE_PAY })).toBeInTheDocument()
  expect(createCheckout).toHaveBeenCalledTimes(1)
})

test('checkout_pending GET renders 待支付, not 已开通', async () => {
  ;(previewCheckout as jest.Mock).mockResolvedValue({
    product: 'relay', channels: BOTH_ON, empty_state: null, can_pay: true, order_id: 7,
  })
  ;(listMyOrders as jest.Mock).mockResolvedValue([
    { id: 7, status: 'checkout_pending', channel: 'alipay', product_code: 'relay', amount_cents: 9900 },
  ])
  renderCheckout('/billing/checkout?product=relay')
  expect(await screen.findByText(CHECKOUT_PENDING_COPY)).toBeInTheDocument()
  expect(screen.getByText(CHANNEL_ALIPAY)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: CHECKOUT_GO_PAY })).toBeNull()
  expect(screen.getByRole('button', { name: CHECKOUT_CONTINUE_PAY })).toBeInTheDocument()
  expect(document.body.textContent).not.toContain('已开通')
  expect(createCheckout).not.toHaveBeenCalled()
  expect(previewCheckout).toHaveBeenCalledWith('relay')
})

test('paid_pending_fulfillment shows 支付已到账，开通处理中, no 去支付', async () => {
  ;(previewCheckout as jest.Mock).mockResolvedValue({
    product: 'plan_pro', channels: BOTH_ON, empty_state: null, can_pay: true, order_id: 8,
  })
  ;(listMyOrders as jest.Mock).mockResolvedValue([
    { id: 8, status: 'paid_pending_fulfillment', channel: 'wechat', product_code: 'plan_pro', amount_cents: 29900 },
  ])
  renderCheckout()
  expect(await screen.findByText(CHECKOUT_PAID_PENDING_COPY)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: CHECKOUT_GO_PAY })).toBeNull()
  expect(screen.queryByRole('button', { name: CHECKOUT_CONTINUE_PAY })).toBeNull()
  expect(document.body.textContent).not.toContain('已开通专业档')
  expect(createCheckout).not.toHaveBeenCalled()
})

test('only wechat unconfigured: 该通道未开通 beside wechat; alipay can 去支付', async () => {
  ;(previewCheckout as jest.Mock).mockResolvedValue({
    product: 'plan_pro', channels: ONLY_ALIPAY, empty_state: null, can_pay: true, order_id: null,
  })
  renderCheckout()
  await screen.findByTestId('channel-wechat')
  expect(screen.getByText(CHANNEL_UNCONFIGURED_COPY)).toBeInTheDocument()
  expect(screen.getByRole('radio', { name: /微信支付/ })).toBeDisabled()
  expect(screen.getByRole('button', { name: CHECKOUT_GO_PAY })).toBeEnabled()
})

test('POST unconfigured wechat maps 该通道未开通 and does not look like 5xx', async () => {
  ;(previewCheckout as jest.Mock).mockResolvedValue({
    product: 'plan_pro', channels: ONLY_ALIPAY, empty_state: null, can_pay: true, order_id: null,
  })
  ;(createCheckout as jest.Mock).mockRejectedValue({
    response: {
      status: 422,
      data: { code: 'BILLING_CHANNEL_UNCONFIGURED', message: CHANNEL_UNCONFIGURED_COPY },
    },
  })
  renderCheckout()
  fireEvent.click(await screen.findByRole('button', { name: CHECKOUT_GO_PAY }))
  expect(await screen.findByText(CHANNEL_UNCONFIGURED_COPY)).toBeInTheDocument()
  expect(screen.queryByText('结账打开失败，请稍后重试。')).toBeNull()
})

test('operator/readonly GET ORDER_ROLE_NOT_ALLOWED is contact admin, no pay', async () => {
  ;(previewCheckout as jest.Mock).mockRejectedValueOnce({
    response: {
      status: 400,
      data: { code: 'ORDER_ROLE_NOT_ALLOWED', message: CONTACT_ADMIN_COPY },
    },
  })
  renderCheckout()
  expect(await screen.findByText(CONTACT_ADMIN_COPY)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: CHECKOUT_GO_PAY })).toBeNull()
  expect(createCheckout).not.toHaveBeenCalled()
  expect(createOrder).not.toHaveBeenCalled()
})

test('illegal product plan_ent is 没有这个商品, no POST', async () => {
  renderCheckout('/billing/checkout?product=plan_ent')
  expect(await screen.findByText(CHECKOUT_UNKNOWN_PRODUCT)).toBeInTheDocument()
  expect(previewCheckout).not.toHaveBeenCalled()
  expect(createCheckout).not.toHaveBeenCalled()
})
