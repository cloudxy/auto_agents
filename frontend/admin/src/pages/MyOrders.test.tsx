/**
 * T-03 我的订单（GWT-50.3/50.4 UI 面）：
 * - 列表=档位名 / 状态中文（pending→待确认收款、paid→已确认）/ 金额**元**
 *   （直渲染 amount_yuan，不做分→元心算；不写「配额已变为专业档」履约句）。
 * - 真 0 空=「还没有升级申请。」+ 说明 + 次链（去用量 / 看定价）；禁止表格默认「暂无数据」。
 * - 失败≠空（FR-84）：「订单列表加载失败。检查网络后重试。」+ 可点重试，重试真拉。
 */
import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import MyOrders from './MyOrders'
import { listMyOrders } from '../services/billing'
import type { OrderRow } from '../services/billing'

jest.mock('../services/billing', () => ({
  listMyOrders: jest.fn(),
}))

const rows: OrderRow[] = [
  { id: 9, plan_id: 2, plan_name: '专业档', amount_cents: 29900, amount_yuan: 299, status: 'pending', channel: 'offline' },
  { id: 5, plan_id: 2, plan_name: '专业档', amount_cents: 29900, amount_yuan: 299, status: 'paid', channel: 'offline' },
]

function renderOrders() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <MyOrders />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  ;(listMyOrders as jest.Mock).mockReset()
})

test('GWT-50.3 / T-09 renders plan name, 待支付/已开通 and yuan amount without cents math', async () => {
  ;(listMyOrders as jest.Mock).mockResolvedValueOnce([
    { ...rows[0], status: 'checkout_pending' },
    { ...rows[1], status: 'fulfilled' },
  ])
  renderOrders()
  expect((await screen.findAllByText('专业档', {}, { timeout: 15000 })).length).toBe(2)
  expect(screen.getByText('待支付')).toBeInTheDocument()
  expect(screen.getByText('已开通')).toBeInTheDocument()
  expect(screen.getAllByText(/299\s*元/).length).toBe(2)
  const copy = document.body.textContent || ''
  expect(copy).not.toContain('29900')
  expect(copy).not.toContain('已确认')
  expect(copy).not.toContain('待确认收款')
  expect(copy).not.toContain('开通处理中')
  expect(copy).not.toContain('未完成')
  expect(copy).not.toContain('当前可买')
  expect(copy).not.toContain('支付已通')
})

test('T-09 empty orders are not failure and have 去结账, no 还没有升级申请', async () => {
  ;(listMyOrders as jest.Mock).mockResolvedValueOnce([])
  renderOrders()
  const go = await screen.findByRole('link', { name: '去结账' })
  expect(go).toHaveAttribute('href', '/billing/checkout?product=plan_pro')
  expect(screen.queryByText('还没有升级申请。')).toBeNull()
  expect(screen.queryByText(/暂无数据/)).toBeNull()
  expect(screen.queryByText(/暂无订单/)).toBeNull()
  expect(document.body.textContent || '').not.toContain('已确认')
})

test('FR-84 order list failure shows failure sentence + retry, retry refetches', async () => {
  ;(listMyOrders as jest.Mock).mockRejectedValueOnce(new Error('network down'))
  renderOrders()
  expect(
    await screen.findByText('订单列表加载失败。检查网络后重试。', {}, { timeout: 15000 }),
  ).toBeInTheDocument()
  expect(screen.queryByText(/暂无数据/)).toBeNull()
  expect(screen.queryByText(/还没有升级申请/)).toBeNull()

  ;(listMyOrders as jest.Mock).mockResolvedValueOnce(rows)
  fireEvent.click(screen.getByRole('button', { name: /重\s*试/ }))
  await waitFor(() => expect(listMyOrders).toHaveBeenCalledTimes(2))
  expect((await screen.findAllByText('专业档')).length).toBe(2)
})
