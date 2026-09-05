/**
 * 租户用量 service（工单 71 归一）
 */
import api, { unwrap } from './api'

export interface UsageOverview {
  tenant_id: number
  quota: { task_concurrency: number; result_storage: number; llm_tokens_month: number }
  usage: { task_concurrency: number; result_storage: number; llm_tokens_month: number }
  llm_by_provider: Record<string, number>
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
