/**
 * 平台运营域 service（SaaS S5-2，工单 71 归一）：租户列表与配额/状态管理
 */
import api, { unwrap } from './api'

export interface TenantRow {
  id: number
  slug: string
  name: string
  status: string
  quota: { task_concurrency?: number; result_storage?: number; llm_tokens_month?: number } | null
  expires_at: string | null
  created_at?: string | null
}

export const listTenants = (): Promise<TenantRow[]> =>
  api.get('/admin/tenants').then((r) => unwrap<TenantRow[]>(r))

export const patchTenant = (id: number, payload: Record<string, unknown>): Promise<void> =>
  api.patch(`/admin/tenants/${id}`, payload).then(() => undefined)
