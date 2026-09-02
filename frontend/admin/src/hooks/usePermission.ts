/**
 * 权限控制 Hook - 消费后端 /permissions 下发（R5 单真相源）
 *
 * 登录/刷新时经 refreshPermissions() 拉取当前角色权限码缓存到本模块
 * （非 Zustand 持久化——权限随 token 生命周期，重登自动刷新）。
 * 后端 _ROLE_PERMISSIONS 是唯一权威源（auth.py）。
 */
import { useAuthStore } from '../store/useAuthStore'
import { menuConfig } from '../config/menuConfig'
import type { MenuItem } from '../config/menuConfig'
import api from '../services/api'

// 模块级缓存（登录后由 refreshPermissions 填充；未登录时为空数组=全只读）
let cachedPermissions: string[] = []

export const refreshPermissions = async (): Promise<string[]> => {
  try {
    const resp = await api.get('/auth/permissions')
    const body = resp as unknown as { data?: string[] }
    cachedPermissions = Array.isArray(body?.data) ? body.data : []
  } catch {
    cachedPermissions = []
  }
  return cachedPermissions
}

export const usePermission = () => {
  const { user } = useAuthStore()
  const role = user?.role || (user?.is_admin ? 'admin' : 'viewer')

  // 下发未就绪时兜底：菜单全部隐藏（安全侧），按钮全禁
  const permissions = cachedPermissions

  const hasPermission = (code: string) => permissions.includes(code)

  const filterMenu = (menus: MenuItem[]): MenuItem[] => {
    return menus
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
    permissions,
    filteredMenus: filterMenu(menuConfig),
  }
}
