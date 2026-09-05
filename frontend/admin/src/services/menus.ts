/**
 * 动态菜单 service（menus 表 /auth/menus 下发；空=回退前端静态配置）
 */
import api, { unwrap } from './api'

export interface DynamicMenuNode {
  key: string
  label: string
  icon?: string | null
  permission?: string | null
  tenantOnly?: boolean
  children: DynamicMenuNode[]
}

export const fetchDynamicMenus = (): Promise<DynamicMenuNode[]> =>
  api.get('/auth/menus').then((r) => unwrap<DynamicMenuNode[]>(r) ?? [])
