/**
 * T-09 / FR-M10·M11：结账租户闭集仅待支付/已开通；主钮「提交开通」；
 * 未配通道仍可提交；409「已有待支付」。禁 live 收银台。
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

const GOLD_SUBMIT = '提交开通'
const GOLD_PENDING = '待支付'
const GOLD_FULFILLED = '已开通'
const GOLD_DUP = '已有待支付'
const GOLD_WAIT = '收款通道未开通，提交后等待平台确认开通'
const GOLD_CONTACT = '请联系本企业管理员开通'
const FORBIDDEN = [
  '已有未完成的支付',
  '已确认',
  '开通处理中',
  '未完成',
  '支付未完成，套餐未开通',
  '当前可买',
  '支付已通',
] as const

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

function pageCopy(): string {
  return document.body.textContent || ''
}

function assertNoForbidden() {
  const copy = pageCopy()
  FORBIDDEN.forEach((s) => expect(copy).not.toContain(s))
  expect(screen.queryByRole('button', { name: /取消/ })).toBeNull()
}

beforeEach(() => {
  ;(previewCheckout as jest.Mock).mockReset()
  ;(createCheckout as jest.Mock).mockReset()
  ;(createOrder as jest.Mock).mockReset()
  ;(listMyOrders as jest.Mock).mockReset()
  ;(listMyOrders as jest.Mock).mockResolvedValue([])
})

test('GWT-M11.2 unconfigured open: product + 提交开通, not empty 收款通道未开通 page', async () => {
  ;(previewCheckout as jest.Mock).mockResolvedValueOnce({
    product: 'plan_pro',
    channels: NONE,
    empty_state: '收款通道未开通',
    can_pay: false,
    order_id: null,
    amount_cents: 29900,
  })
  renderCheckout()
  expect(await screen.findByText('专业档')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: GOLD_SUBMIT })).toBeEnabled()
  expect(pageCopy()).toContain('¥299')
  expect(screen.queryByRole('button', { name: '去支付' })).toBeNull()
  expect(screen.queryByRole('radio')).toBeNull()
  expect(createCheckout).not.toHaveBeenCalled()
  expect(createOrder).not.toHaveBeenCalled()
  assertNoForbidden()
})

test('GWT-M11.1 unconfigured submit creates 待支付 and wait-confirm copy', async () => {
  const pendingPreview = {
    product: 'plan_pro',
    channels: NONE,
    empty_state: GOLD_WAIT,
    notice: GOLD_WAIT,
    can_pay: false,
    order_id: 11,
    amount_cents: 29900,
  }
  ;(previewCheckout as jest.Mock)
    .mockResolvedValueOnce({
      product: 'plan_pro', channels: NONE, empty_state: '收款通道未开通', can_pay: false, order_id: null, amount_cents: 29900,
    })
    .mockResolvedValue(pendingPreview)
  ;(createCheckout as jest.Mock).mockResolvedValue({
    id: 11, status: 'checkout_pending', product_code: 'plan_pro', amount_cents: 29900,
  })
  ;(listMyOrders as jest.Mock).mockResolvedValue([
    { id: 11, status: 'checkout_pending', product_code: 'plan_pro', amount_cents: 29900, amount_yuan: 299 },
  ])
  renderCheckout()
  fireEvent.click(await screen.findByRole('button', { name: GOLD_SUBMIT }))
  await waitFor(() => expect(createCheckout).toHaveBeenCalledWith({ product: 'plan_pro' }))
  expect(createOrder).not.toHaveBeenCalled()
  expect(await screen.findByText(GOLD_PENDING)).toBeInTheDocument()
  expect(screen.getByText(GOLD_WAIT)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: GOLD_SUBMIT })).toBeNull()
  expect(screen.queryByRole('button', { name: '去支付' })).toBeNull()
  assertNoForbidden()
})

test('GWT-M11.1 pending gold wait from notice when can_pay is not false', async () => {
  ;(previewCheckout as jest.Mock).mockResolvedValue({
    product: 'plan_pro',
    channels: [{ channel: 'alipay', configured: true, selectable: true }],
    empty_state: GOLD_WAIT,
    notice: GOLD_WAIT,
    can_pay: true,
    order_id: 12,
    amount_cents: 29900,
  })
  ;(listMyOrders as jest.Mock).mockResolvedValue([
    { id: 12, status: 'checkout_pending', product_code: 'plan_pro', amount_cents: 29900, amount_yuan: 299 },
  ])
  renderCheckout()
  expect(await screen.findByText(GOLD_PENDING)).toBeInTheDocument()
  expect(screen.getByText(GOLD_WAIT)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: GOLD_SUBMIT })).toBeNull()
  assertNoForbidden()
})

test('GWT-M11.1 pending gold wait when all channels configured=false', async () => {
  ;(previewCheckout as jest.Mock).mockResolvedValue({
    product: 'plan_pro',
    channels: NONE,
    empty_state: null,
    notice: null,
    can_pay: true,
    order_id: 13,
    amount_cents: 29900,
  })
  ;(listMyOrders as jest.Mock).mockResolvedValue([
    { id: 13, status: 'checkout_pending', product_code: 'plan_pro', amount_cents: 29900, amount_yuan: 299 },
  ])
  renderCheckout()
  expect(await screen.findByText(GOLD_PENDING)).toBeInTheDocument()
  expect(screen.getByText(GOLD_WAIT)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: GOLD_SUBMIT })).toBeNull()
  assertNoForbidden()
})

test('GWT-M11.8 duplicate submit is 已有待支付, never 已有未完成的支付', async () => {
  ;(previewCheckout as jest.Mock).mockResolvedValue({
    product: 'plan_pro', channels: NONE, empty_state: null, can_pay: false, order_id: null, amount_cents: 29900,
  })
  ;(createCheckout as jest.Mock).mockRejectedValue({
    response: { status: 409, data: { code: 'ORDER_PENDING_EXISTS', message: GOLD_DUP } },
  })
  renderCheckout()
  fireEvent.click(await screen.findByRole('button', { name: GOLD_SUBMIT }))
  expect(await screen.findByText(GOLD_DUP)).toBeInTheDocument()
  expect(pageCopy()).not.toContain('已有未完成的支付')
  expect(createCheckout).toHaveBeenCalledTimes(1)
  expect(createOrder).not.toHaveBeenCalled()
  assertNoForbidden()
})

test('GWT-M11.3 operator GET is 请联系本企业管理员开通, no order', async () => {
  ;(previewCheckout as jest.Mock).mockRejectedValueOnce({
    response: { status: 422, data: { code: 'ORDER_ROLE_NOT_ALLOWED', message: GOLD_CONTACT } },
  })
  renderCheckout()
  expect(await screen.findByText(GOLD_CONTACT)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: GOLD_SUBMIT })).toBeNull()
  expect(createCheckout).not.toHaveBeenCalled()
  expect(createOrder).not.toHaveBeenCalled()
  assertNoForbidden()
})

test('checkout_pending renders 待支付, no cancel, no 已开通', async () => {
  ;(previewCheckout as jest.Mock).mockResolvedValue({
    product: 'relay', channels: NONE, empty_state: null, can_pay: false, order_id: 7, amount_cents: 9900,
  })
  ;(listMyOrders as jest.Mock).mockResolvedValue([
    { id: 7, status: 'checkout_pending', product_code: 'relay', amount_cents: 9900, amount_yuan: 99 },
  ])
  renderCheckout('/billing/checkout?product=relay')
  expect(await screen.findByText(GOLD_PENDING)).toBeInTheDocument()
  expect(screen.getByText('中转')).toBeInTheDocument()
  expect(pageCopy()).not.toContain('¥299')
  expect(screen.queryByRole('button', { name: GOLD_SUBMIT })).toBeNull()
  expect(pageCopy()).not.toContain('已开通')
  expect(createCheckout).not.toHaveBeenCalled()
  assertNoForbidden()
})

test('fulfilled renders 已开通, not 已确认', async () => {
  ;(previewCheckout as jest.Mock).mockResolvedValue({
    product: 'plan_pro', channels: NONE, empty_state: null, can_pay: false, order_id: 8, amount_cents: 29900,
  })
  ;(listMyOrders as jest.Mock).mockResolvedValue([
    { id: 8, status: 'fulfilled', product_code: 'plan_pro', amount_cents: 29900, amount_yuan: 299 },
  ])
  renderCheckout()
  expect(await screen.findByText(GOLD_FULFILLED)).toBeInTheDocument()
  expect(pageCopy()).not.toContain('已确认')
  expect(screen.queryByRole('button', { name: GOLD_SUBMIT })).toBeNull()
  assertNoForbidden()
})

test('paid_pending_fulfillment does not render 开通处理中', async () => {
  ;(previewCheckout as jest.Mock).mockResolvedValue({
    product: 'plan_pro', channels: NONE, empty_state: null, can_pay: false, order_id: 8, amount_cents: 29900,
  })
  ;(listMyOrders as jest.Mock).mockResolvedValue([
    { id: 8, status: 'paid_pending_fulfillment', product_code: 'plan_pro', amount_cents: 29900 },
  ])
  renderCheckout()
  expect(await screen.findByTestId('checkout-page')).toBeInTheDocument()
  expect(pageCopy()).not.toContain('开通处理中')
  expect(pageCopy()).not.toContain('支付已到账')
  assertNoForbidden()
})

test('illegal product is 没有这个商品, no POST', async () => {
  renderCheckout('/billing/checkout?product=plan_ent')
  expect(await screen.findByText('没有这个商品。')).toBeInTheDocument()
  expect(previewCheckout).not.toHaveBeenCalled()
  expect(createCheckout).not.toHaveBeenCalled()
})
