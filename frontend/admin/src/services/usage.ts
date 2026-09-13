/**
 * 租户用量 service（工单 71 归一）
 */
import api, { unwrap } from './api'

export interface UsageAlert {
  metric: string
  level: 'near' | 'full' | 'error' | string
  message: string
}

export interface UsageOverview {
  tenant_id?: number
  quota?: { task_concurrency: number; result_storage: number; llm_tokens_month: number }
  usage?: { task_concurrency: number; result_storage: number; llm_tokens_month: number }
  llm_by_provider?: Record<string, number>
  timezone?: string
  year_month?: string
  alerts?: UsageAlert[]
  scope?: string
  message?: string
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

export interface UpgradeIntent {
  action: 'checkout' | 'contact_admin' | string
  product: string
  checkout_path: string | null
  message: string
}

/** T-03 GET /tenants/me/quota/upgrade-intent：分角色着陆，不建单。 */
export const fetchUpgradeIntent = (product = 'plan_pro'): Promise<UpgradeIntent> =>
  api.get('/tenants/me/quota/upgrade-intent', { params: { product } }).then((r) => unwrap<UpgradeIntent>(r))
