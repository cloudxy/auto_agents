/**
 * 角色与部门 service（SaaS 化：权限矩阵 / 组织树）
 */
import api, { unwrap } from './api'

export interface RoleRow {
  id: number | null
  role_key: string
  name: string
  description?: string | null
  permissions: string[]
  is_builtin: boolean
}

export interface PermissionCode {
  code: string
  group: string
  label: string
}

export const listRoles = (): Promise<{ roles: RoleRow[]; catalog: PermissionCode[] }> =>
  api.get('/rbac/roles').then((r) => unwrap<{ roles: RoleRow[]; catalog: PermissionCode[] }>(r))

export const updateRole = (roleKey: string, payload: Partial<Pick<RoleRow, 'name' | 'description' | 'permissions'>>): Promise<void> =>
  api.put(`/rbac/roles/${roleKey}`, payload).then(() => undefined)

export interface DepartmentRow {
  id: number
  tenant_id: number
  name: string
  description?: string | null
  member_count: number
}

export const listDepartments = (tenantId: number): Promise<DepartmentRow[]> =>
  api.get('/rbac/departments', { params: { tenant_id: tenantId } }).then((r) => unwrap<DepartmentRow[]>(r))

export const createDepartment = (payload: { tenant_id: number; name: string; description?: string }): Promise<{ id: number }> =>
  api.post('/rbac/departments', payload).then((r) => unwrap<{ id: number }>(r))

export const updateDepartment = (id: number, payload: { name?: string; description?: string }): Promise<void> =>
  api.put(`/rbac/departments/${id}`, payload).then(() => undefined)

export const deleteDepartment = (id: number): Promise<void> =>
  api.delete(`/rbac/departments/${id}`).then(() => undefined)
