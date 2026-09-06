/**
 * 租户用量 service（工单 71 归一）
 */
import api, { unwrap } from './api'

export interface UsageOverview {
  tenant_id: number
  quota: { task_concurrency: number; result_storage: number; llm_tokens_month: number }
  usage: { task_concurrency: number; result_storage: number; llm_tokens_month: number }
  llm_by_provider: Record<string, number>
  cost_by_provider: Record<string, number>
  cost_cents_total: number
}

export const fetchUsageOverview = (): Promise<UsageOverview> =>
  api.get('/tenants/me/usage').then((r) => unwrap<UsageOverview>(r))

export interface MemberUsageRow {
  member: string
  tasks: number
  last_active_at: string | null
}

/** 成员维度用量分摊（B6 工单 91） */
export const fetchUsageByMember = (): Promise<MemberUsageRow[]> =>
  api.get('/tenants/me/usage/by-member').then((r) => unwrap<MemberUsageRow[]>(r))

export interface DeliveryWebhook {
  delivery_webhook_url: string | null
}

export const fetchDeliveryWebhook = (): Promise<DeliveryWebhook> =>
  api.get('/tenants/me/delivery-webhook').then((r) => unwrap<DeliveryWebhook>(r))

export const putDeliveryWebhook = (url: string | null): Promise<DeliveryWebhook> =>
  api.put('/tenants/me/delivery-webhook', { url }).then((r) => unwrap<DeliveryWebhook>(r))
