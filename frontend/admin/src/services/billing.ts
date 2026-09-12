import api, { unwrap } from './api'

export interface PlanRow {
  id: number
  slug: string
  name: string
  price_cents: number
  period: string
}

export interface OrderRow {
  id: number
  plan_id: number
  amount_cents: number
  status: string
  channel: string
  /** T-02 读模型：档位名（如「专业档」） */
  plan_name?: string
  /** T-02 读模型：金额（元，与定价页同一数字）。渲染用它，不做分→元心算 */
  amount_yuan?: number
  tenant_name?: string
}

export const listPlans = (): Promise<PlanRow[]> =>
  api.get('/billing/plans').then((r) => unwrap<PlanRow[]>(r))

export const listMyOrders = (): Promise<OrderRow[]> =>
  api.get('/billing/orders').then((r) => unwrap<OrderRow[]>(r))

export const createOrder = (plan_id: number): Promise<OrderRow> =>
  api.post('/billing/orders', { plan_id, channel: 'offline' }).then((r) => unwrap<OrderRow>(r))

export const listPendingOrders = (): Promise<OrderRow[]> =>
  api.get('/billing/admin/orders').then((r) => unwrap<OrderRow[]>(r))

export const confirmOrder = (orderId: number): Promise<OrderRow> =>
  api.post(`/billing/orders/${orderId}/confirm`).then((r) => unwrap<OrderRow>(r))
