import api, { unwrap } from './api'

export interface PlanRow {
  id: number
  slug: string
  name: string
  price_cents: number
  period: string
}

export type PayChannel = 'alipay' | 'wechat'
export type CheckoutProduct = 'plan_pro' | 'plan_enterprise' | 'relay'

export interface OrderRow {
  id: number
  plan_id?: number | null
  amount_cents: number
  status: string
  channel: string
  /** T-02 读模型：档位名（如「专业档」） */
  plan_name?: string
  /** T-02 读模型：金额（元，与定价页同一数字）。渲染用它，不做分→元心算 */
  amount_yuan?: number
  tenant_name?: string
  product_code?: string | null
}

export interface CheckoutChannel {
  channel: PayChannel
  configured: boolean
  selectable: boolean
}

export const listPlans = (): Promise<PlanRow[]> =>
  api.get('/billing/plans').then((r) => unwrap<PlanRow[]>(r))

export interface CheckoutPreview {
  product: string
  channels: CheckoutChannel[]
  empty_state: string | null
  can_pay: boolean
  order_id: number | null
  amount_cents?: number | null
}

/** T-16 GET /billing/checkout：通道选择 + 空态；不建单、无 notify。 */
export const previewCheckout = (product = 'plan_pro'): Promise<CheckoutPreview> =>
  api.get('/billing/checkout', { params: { product } }).then((r) => unwrap<CheckoutPreview>(r))

/** T-16 POST /billing/checkout：买方占坑。channel 闭集 alipay|wechat。 */
export const createCheckout = (body: {
  product: string
  channel: PayChannel
}): Promise<OrderRow> =>
  api.post('/billing/checkout', body).then((r) => unwrap<OrderRow>(r))

export const listMyOrders = (): Promise<OrderRow[]> =>
  api.get('/billing/orders').then((r) => unwrap<OrderRow[]>(r))

export const createOrder = (plan_id: number): Promise<OrderRow> =>
  api.post('/billing/orders', { plan_id, channel: 'offline' }).then((r) => unwrap<OrderRow>(r))

export const listPendingOrders = (): Promise<OrderRow[]> =>
  api.get('/billing/admin/orders').then((r) => unwrap<OrderRow[]>(r))

export const confirmOrder = (orderId: number): Promise<OrderRow> =>
  api.post(`/billing/orders/${orderId}/confirm`).then((r) => unwrap<OrderRow>(r))
