/**
 * 平台用户管理 service（工单：用户管理页 CRUD/权限分配/公司归属）
 */
import api, { unwrap } from './api'

export interface UserItem {
  id: number
  username: string
  email: string
  is_active: boolean
  is_admin: boolean
  role?: string
  tenant_id?: number | null
  tenant_name?: string | null
  tenant_role?: string | null
  department_id?: number | null
  department_name?: string | null
  is_platform_admin?: boolean
  created_at?: string | null
}

export interface UserCreatePayload {
  username: string
  email: string
  password: string
  role: string
  tenant_id?: number | null
}

export interface UserUpdatePayload {
  role?: string
  is_active?: boolean
  tenant_id?: number | null
  department_id?: number | null
}

export const createUser = (payload: UserCreatePayload): Promise<UserItem> =>
  api.post('/admin/users', payload).then((r) => unwrap<UserItem>(r))

export const updateUser = (id: number, payload: UserUpdatePayload): Promise<UserItem> =>
  api.patch(`/admin/users/${id}`, payload).then((r) => unwrap<UserItem>(r))

export const deleteUser = (id: number): Promise<void> =>
  api.delete(`/admin/users/${id}`).then(() => undefined)

export interface NotifyChannelConfig {
  webhook_url: string
  dingtalk_url: string
  wechat_work_url: string
}

export const fetchNotifyConfig = (): Promise<NotifyChannelConfig> =>
  api.get('/admin/notify-config').then((r) => unwrap<NotifyChannelConfig>(r))

export const updateNotifyConfig = (payload: Partial<NotifyChannelConfig>): Promise<void> =>
  api.put('/admin/notify-config', payload).then(() => undefined)
