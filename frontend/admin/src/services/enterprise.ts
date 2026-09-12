/**
 * 企业管理 service：租户最小创建（配额/到期走平台运营台）+ 改名/账户状态（T-28/FR-95）
 *
 * 写动作与运营台同打 PATCH /admin/tenants/{id}（tenant_admin_service 单点收口，T-27），
 * 两处读同一 GET /admin/tenants —— 一处写、两处同显（GWT-95.1/95.2/95.7 同真相）。
 */
import api, { unwrap } from './api'

export interface TenantRow {
  id: number
  slug: string
  name: string
  status: string
  expires_at: string | null
  /** 平台默认租户标注（T-27 后端下发；GWT-95.3「默认归属」Tag 数据源） */
  is_platform_default?: boolean
}

export const listTenants = (): Promise<TenantRow[]> =>
  api.get('/admin/tenants').then((r) => unwrap<TenantRow[]>(r))

export const createTenantMinimal = (payload: { name: string; slug?: string }): Promise<{ id: number; slug: string }> =>
  api.post('/admin/tenants', payload).then((r) => unwrap<{ id: number; slug: string }>(r))

/** 企业改名（GWT-95.1）：冲突 400 中文句（「企业名称不可用: {name}」）由调用方原样呈现 */
export const renameTenant = (id: number, name: string): Promise<void> =>
  api.patch(`/admin/tenants/${id}`, { name }).then(() => undefined)

/** 账户状态双向流转（GWT-95.2/95.7）：仅常规企业（平台租户由后端守卫拒绝，GWT-94.3） */
export const setTenantStatus = (id: number, status: 'active' | 'disabled'): Promise<void> =>
  api.patch(`/admin/tenants/${id}`, { status }).then(() => undefined)
