import api, { unwrap } from './api'

export interface PlanRow {
  id: number
  slug: string
  name: string
  price_cents: number
  period: string
  quota_json?: string | null
  is_public?: number
}

export type PayChannel = 'offline' | 'alipay' | 'wechat'
export type CheckoutProduct = 'plan_pro' | 'plan_enterprise' | 'relay'

export const CHANNEL_LABEL: Record<string, string> = {
  offline: '线下转账',
  alipay: '支付宝',
  wechat: '微信支付',
}

export interface OrderRow {
  id: number
  plan_id?: number | null
  amount_cents: number
  status: string
  channel: string
  paid_at?: string | null
  created_at?: string
  tenant_id?: number | null
  /** T-02 读模型：档位名（如「专业档」） */
  plan_name?: string
  /** T-02 读模型：金额（元，与定价页同一数字）。渲染用它，不做分→元心算 */
  amount_yuan?: number
  tenant_name?: string
  product_code?: string | null
  order_no?: string | null
  /** 在线支付真实网关产出：channel 已配商户凭据且网关调用成功才有值；
   * 未配置/网关调用失败为 null——照常走人工确认收款，不阻断下单 */
  pay_url?: string | null
  qr_code_url?: string | null
  qr_code_image?: string | null
}

export interface SubscriptionRow {
  id: number
  plan_id: number
  status: string
  current_period_end: string | null
  tenant_id: number | null
}

export interface CheckoutChannel {
  channel: Exclude<PayChannel, 'offline'>
  configured: boolean
  selectable: boolean
}

export const listPlans = (): Promise<PlanRow[]> =>
  api.get('/billing/plans').then((r) => unwrap<PlanRow[]>(r) ?? [])

export const fetchSubscription = (): Promise<SubscriptionRow | null> =>
  api.get('/billing/subscription').then((r) => unwrap<SubscriptionRow | null>(r) ?? null)

export interface CheckoutPreview {
  product: string
  channels: CheckoutChannel[]
  empty_state: string | null
  notice?: string | null
  can_pay: boolean
  order_id: number | null
  amount_cents?: number | null
}

/** T-16 GET /billing/checkout：通道选择 + 空态；不建单、无 notify。 */
export const previewCheckout = (product = 'plan_pro'): Promise<CheckoutPreview> =>
  api.get('/billing/checkout', { params: { product } }).then((r) => unwrap<CheckoutPreview>(r))

/** POST /billing/checkout：W2 不要求已选通道。 */
export const createCheckout = (body: {
  product: string
  channel?: Exclude<PayChannel, 'offline'>
}): Promise<OrderRow> =>
  api.post('/billing/checkout', body).then((r) => unwrap<OrderRow>(r))

export const listMyOrders = (): Promise<OrderRow[]> =>
  api.get('/billing/orders').then((r) => unwrap<OrderRow[]>(r) ?? [])

/** 按需重取在线支付链接/二维码（未持久化，每次现取现签，见后端
 * BillingService.regenerate_pay_intent）。channel 未配置/网关失败时
 * pay_url/qr_code_url 仍是 null，不算请求失败。 */
export const fetchPayIntent = (orderId: number): Promise<OrderRow> =>
  api.get(`/billing/orders/${orderId}/pay-intent`).then((r) => unwrap<OrderRow>(r))

export const createOrder = (plan_id: number, channel: PayChannel = 'offline'): Promise<OrderRow> =>
  api.post('/billing/orders', { plan_id, channel }).then((r) => unwrap<OrderRow>(r))

export const listPendingOrders = (): Promise<OrderRow[]> =>
  api.get('/billing/admin/orders').then((r) => unwrap<OrderRow[]>(r) ?? [])

export const confirmOrder = (orderId: number): Promise<OrderRow> =>
  api.post(`/billing/orders/${orderId}/confirm`).then((r) => unwrap<OrderRow>(r))
