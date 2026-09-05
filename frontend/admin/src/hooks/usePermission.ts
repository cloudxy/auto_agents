/**
 * 权限控制 Hook - 消费后端 /permissions 下发（R5 单真相源）
 *
 * 后端 _ROLE_PERMISSIONS 是唯一权威源（auth.py）。权限码缓存到本模块
 * （非 Zustand 持久化——权限随 token 生命周期）。
 *
 * 缓存生命周期（侧边栏缺失修复）：
 * - login() 成功时主动拉取（useAuthStore 调 refreshPermissions）
 * - 页面刷新（F5）后 token 由 persist 恢复、模块缓存归零——hook 挂载时
 *   检测「已登录但缓存空」自动补拉（in-flight 去重），拉取完成后经
 *   revision state 触发重渲染（模块级数组变更本身不触发 React 更新）
 * - logout() 清空（clearCachedPermissions），防跨账号残留
 */
import { useEffect, useState } from 'react'
import { useAuthStore } from '../store/useAuthStore'
import { menuConfig } from '../config/menuConfig'
import type { MenuItem } from '../config/menuConfig'
import api from '../services/api'

// 模块级缓存（未登录/未就绪时为空数组=菜单全隐、按钮全禁，安全侧）
let cachedPermissions: string[] = []
let refreshInFlight: Promise<string[]> | null = null

export const refreshPermissions = async (): Promise<string[]> => {
  if (refreshInFlight) return refreshInFlight
  refreshInFlight = (async () => {
    try {
      const resp = await api.get('/auth/permissions')
      const body = resp as unknown as { data?: string[] }
      cachedPermissions = Array.isArray(body?.data) ? body.data : []
    } catch {
      cachedPermissions = []
    } finally {
      refreshInFlight = null
    }
    return cachedPermissions
  })()
  return refreshInFlight
}

/** 登出清缓存（防跨账号权限残留；下次登录经 login() 重新拉取） */
export const clearCachedPermissions = (): void => {
  cachedPermissions = []
}

export const usePermission = () => {
  const { user, isAuthenticated } = useAuthStore()
  const role = user?.role || (user?.is_admin ? 'admin' : 'viewer')

  // 缓存属模块级，填充后需 bump revision 触发消费方重渲染
  const [revision, setRevision] = useState(0)

  useEffect(() => {
    // 已登录但缓存空（F5 后 persist 恢复登录态的典型场景）→ 自动补拉
    if (!isAuthenticated || cachedPermissions.length > 0) return
    let alive = true
    refreshPermissions().then(() => { if (alive) setRevision((r) => r + 1) })
    return () => { alive = false }
  }, [isAuthenticated])

  const hasPermission = (code: string) => cachedPermissions.includes(code)

  // tenantOnly 过滤（递归到叶子层）：标记实际全在叶子（成员管理/用量看板），
  // 只滤顶层 = 纯平台超管（tenant_id=NULL）在兜底态仍见租户菜单，点击 403（F-T10-1）
  const filterTenantOnly = (menus: MenuItem[], tenantBound: boolean): MenuItem[] =>
    menus
      .filter(menu => !menu.tenantOnly || tenantBound)
      .map(menu => (menu.children
        ? { ...menu, children: filterTenantOnly(menu.children, tenantBound) }
        : menu))
      .filter(menu => !menu.children || menu.children.length > 0)

  const filterMenu = (menus: MenuItem[]): MenuItem[] => {
    void revision
    const tenantBound = user?.tenant_id != null
    // 权限不可知（后端不可达/缓存空）→ 显示全量菜单（admin 视角兜底）
    // 理由：菜单可见性是 UI 优化，真正的安全防线在 API 层（JWT → RBAC → 租户隔离）
    // 此前逻辑：缓存空 → filterMenu 全滤光 → 侧边栏消失（后端重启/网络瞬断即复发）
    if (cachedPermissions.length === 0) {
      return filterTenantOnly(menus, tenantBound)
    }
    return menus
      .filter(menu => !menu.tenantOnly || tenantBound)
      .filter(menu => !menu.permission || hasPermission(menu.permission))
      .map(menu => ({
        ...menu,
        children: menu.children ? filterMenu(menu.children) : undefined
      }))
      .filter(menu => !menu.children || menu.children.length > 0)
  }

  return {
    hasPermission,
    role,
    isAdmin: role === 'admin',
    permissions: cachedPermissions,
    permissionsReady: cachedPermissions.length > 0,
    filteredMenus: filterMenu(menuConfig),
  }
}
