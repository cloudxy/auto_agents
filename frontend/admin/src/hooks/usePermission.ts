/**
 * 权限控制 Hook - 用于菜单和按钮级权限控制（角色与后端 RBAC 对齐）
 */
import { useAuthStore } from '../store/useAuthStore'
import type { MenuItem } from '../config/menuConfig'

// 角色 → 权限码（与后端 /auth/permissions 的 _ROLE_PERMISSIONS 保持一致）
const ROLE_PERMISSIONS: Record<string, string[]> = {
  admin: ['menu:dashboard', 'menu:spiders', 'menu:spiders.tasks', 'menu:spiders.logs', 'menu:spiders.nodes', 'menu:users', 'menu:data', 'menu:settings', 'menu:ai', 'menu:llm', 'menu:newapi', 'menu:logs', 'btn:create', 'btn:delete', 'btn:schedule'],
  operator: ['menu:dashboard', 'menu:spiders', 'menu:spiders.tasks', 'menu:spiders.logs', 'menu:spiders.nodes', 'menu:data', 'menu:ai', 'menu:logs', 'btn:create'],
  viewer: ['menu:dashboard', 'menu:spiders', 'menu:spiders.tasks', 'menu:spiders.logs', 'menu:spiders.nodes', 'menu:ai'],
}

export const usePermission = () => {
  const { user } = useAuthStore()
  // 登录后后端返回 role；兼容旧会话（无 role 时回退 is_admin）
  const role = user?.role || (user?.is_admin ? 'admin' : 'viewer')
  const permissions = ROLE_PERMISSIONS[role] || []

  const hasPermission = (code: string) => permissions.includes(code)

  // 递归过滤菜单树
  const filterMenu = (menus: MenuItem[]): MenuItem[] => {
    return menus
      .filter(menu => !menu.permission || hasPermission(menu.permission))
      .map(menu => ({
        ...menu,
        children: menu.children ? filterMenu(menu.children) : undefined
      }))
      .filter(menu => !menu.children || menu.children.length > 0) // 移除没有子项的父菜单
  }

  return {
    hasPermission,
    role,
    isAdmin: role === 'admin',
    filteredMenus: filterMenu(require('../config/menuConfig').menuConfig),
  }
}
