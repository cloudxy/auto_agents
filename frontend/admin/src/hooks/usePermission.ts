/**
 * 权限控制 Hook - 消费后端 /permissions 下发（R5 单真相源）
 *
 * 空缓存 ≠ 无权限滤光，也 ≠ 全开平台写（T-05 / P-FE-03）：
 * 未就绪显示读叶 +「权限加载中」；平台写叶仅 is_platform_admin。
 */
import { useEffect, useState } from 'react'
import { useAuthStore } from '../store/useAuthStore'
import { menuConfig } from '../config/menuConfig'
import type { MenuItem } from '../config/menuConfig'
import api from '../services/api'

let cachedPermissions: string[] = []
let refreshInFlight: Promise<string[]> | null = null
let loadState: 'unloaded' | 'loading' | 'loaded' | 'error' = 'unloaded'

export const refreshPermissions = async (): Promise<string[]> => {
  if (refreshInFlight) return refreshInFlight
  loadState = 'loading'
  refreshInFlight = (async () => {
    try {
      const resp = await api.get('/auth/permissions')
      const body = resp as unknown as { data?: string[] }
      cachedPermissions = Array.isArray(body?.data) ? body.data : []
      loadState = 'loaded'
    } catch {
      cachedPermissions = []
      loadState = 'error'
    } finally {
      refreshInFlight = null
    }
    return cachedPermissions
  })()
  return refreshInFlight
}

export const clearCachedPermissions = (): void => {
  cachedPermissions = []
  loadState = 'unloaded'
}

const filterTenantOnly = (menus: MenuItem[], tenantBound: boolean): MenuItem[] =>
  menus
    .filter(menu => !menu.tenantOnly || tenantBound)
    .map(menu => (menu.children
      ? { ...menu, children: filterTenantOnly(menu.children, tenantBound) }
      : menu))
    .filter(menu => !menu.children || menu.children.length > 0)

const stripPlatformWrite = (menus: MenuItem[]): MenuItem[] =>
  menus
    .filter(menu => !menu.platformOnly)
    .map(menu => (menu.children
      ? { ...menu, children: stripPlatformWrite(menu.children) }
      : menu))
    .filter(menu => !menu.children || menu.children.length > 0)

export const usePermission = () => {
  const { user, isAuthenticated } = useAuthStore()
  const role = user?.role || (user?.is_admin ? 'admin' : 'viewer')
  const isPlatformAdmin = Boolean(user?.is_platform_admin)
  const [revision, setRevision] = useState(0)

  useEffect(() => {
    if (!isAuthenticated || loadState === 'loaded') return
    let alive = true
    refreshPermissions().then(() => { if (alive) setRevision((r) => r + 1) })
    return () => { alive = false }
  }, [isAuthenticated])

  const hasPermission = (code: string) => cachedPermissions.includes(code)
  void revision

  const filterByPermission = (menus: MenuItem[]): MenuItem[] =>
    menus
      .filter(menu => !menu.tenantOnly || user?.tenant_id != null)
      .filter(menu => !menu.platformOnly || isPlatformAdmin)
      .filter(menu => !menu.permission || hasPermission(menu.permission))
      .map(menu => ({
        ...menu,
        children: menu.children ? filterByPermission(menu.children) : undefined,
      }))
      .filter(menu => !menu.children || menu.children.length > 0)

  const tenantBound = user?.tenant_id != null
  const permissionsReady = loadState === 'loaded'
  const filteredMenus = permissionsReady
    ? filterByPermission(menuConfig)
    : stripPlatformWrite(filterTenantOnly(menuConfig, tenantBound))

  return {
    hasPermission,
    role,
    isAdmin: role === 'admin',
    isPlatformAdmin,
    permissions: cachedPermissions,
    permissionsReady,
    permissionsLoadState: loadState,
    filteredMenus,
  }
}
