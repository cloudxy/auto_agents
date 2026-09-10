/**
 * 企业管理 service：租户最小创建（配额/到期走平台运营台）
 */
import api, { unwrap } from './api'

export interface TenantRow {
  id: number
  slug: string
  name: string
  status: string
  expires_at: string | null
}

export const listTenants = (): Promise<TenantRow[]> =>
  api.get('/admin/tenants').then((r) => unwrap<TenantRow[]>(r))

export const createTenantMinimal = (payload: { name: string; slug?: string }): Promise<{ id: number; slug: string }> =>
  api.post('/admin/tenants', payload).then((r) => unwrap<{ id: number; slug: string }>(r))
