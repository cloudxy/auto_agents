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

export const createRole = (payload: { role_key: string; name: string; description?: string; permissions?: string[] }): Promise<{ role_key: string }> =>
  api.post('/rbac/roles', payload).then((r) => unwrap<{ role_key: string }>(r))

export const deleteRole = (roleKey: string): Promise<void> =>
  api.delete(`/rbac/roles/${roleKey}`).then(() => undefined)

export interface MenuNode {
  id: number
  parent_id: number | null
  name: string
  path: string | null
  icon: string | null
  permission: string | null
  sort_order: number
  visible: boolean
  children: MenuNode[]
}

export const fetchMenuTree = (): Promise<MenuNode[]> =>
  api.get('/rbac/menus/tree').then((r) => unwrap<MenuNode[]>(r))

export const createMenu = (payload: { parent_id?: number | null; name: string; path?: string; icon?: string; permission?: string; sort_order?: number }): Promise<{ id: number }> =>
  api.post('/rbac/menus', payload).then((r) => unwrap<{ id: number }>(r))

export const updateMenu = (id: number, payload: Partial<MenuNode>): Promise<void> =>
  api.put(`/rbac/menus/${id}`, payload).then(() => undefined)

export const deleteMenu = (id: number): Promise<void> =>
  api.delete(`/rbac/menus/${id}`).then(() => undefined)

export interface PermissionRow {
  id: number | string
  code: string
  name: string
  group: string
  ptype?: string
  description?: string | null
}

export const listPermissionResources = (): Promise<PermissionRow[]> =>
  api.get('/rbac/permissions').then((r) => unwrap<PermissionRow[]>(r))

export const createPermissionResource = (payload: { code: string; name: string; group_name?: string; ptype?: string; description?: string }): Promise<{ id: number }> =>
  api.post('/rbac/permissions', payload).then((r) => unwrap<{ id: number }>(r))

export const updatePermissionResource = (id: number, payload: { name?: string; group_name?: string; description?: string }): Promise<void> =>
  api.put(`/rbac/permissions/${id}`, payload).then(() => undefined)

export const deletePermissionResource = (id: number): Promise<void> =>
  api.delete(`/rbac/permissions/${id}`).then(() => undefined)
