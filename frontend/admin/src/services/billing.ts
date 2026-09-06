/**
 * 租户订购 / 平台确认收款
 */
import api, { unwrap } from './api'

export type PayChannel = 'offline' | 'alipay' | 'wechat'

export interface PlanRow {
  id: number
  slug: string
  name: string
  price_cents: number
  period: string
  quota_json: string | null
  is_public: number
}

export interface OrderRow {
  id: number
  plan_id: number
  amount_cents: number
  status: string
  channel: PayChannel | string
  paid_at: string | null
  created_at: string
  tenant_id: number | null
}

export interface SubscriptionRow {
  id: number
  plan_id: number
  status: string
  current_period_end: string | null
  tenant_id: number | null
}

export const CHANNEL_LABEL: Record<string, string> = {
  offline: '线下转账',
  alipay: '支付宝',
  wechat: '微信支付',
}

export const listPlans = (): Promise<PlanRow[]> =>
  api.get('/billing/plans').then((r) => unwrap<PlanRow[]>(r) ?? [])

export const fetchSubscription = (): Promise<SubscriptionRow | null> =>
  api.get('/billing/subscription').then((r) => unwrap<SubscriptionRow | null>(r) ?? null)

export const listMyOrders = (): Promise<OrderRow[]> =>
  api.get('/billing/orders').then((r) => unwrap<OrderRow[]>(r) ?? [])

export const createOrder = (planId: number, channel: PayChannel): Promise<OrderRow> =>
  api.post('/billing/orders', { plan_id: planId, channel }).then((r) => unwrap<OrderRow>(r))

export const listPendingOrders = (): Promise<OrderRow[]> =>
  api.get('/billing/admin/orders').then((r) => unwrap<OrderRow[]>(r) ?? [])

export const confirmOrder = (orderId: number): Promise<OrderRow> =>
  api.post(`/billing/orders/${orderId}/confirm`).then((r) => unwrap<OrderRow>(r))
