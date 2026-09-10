/**
 * 菜单配置 - 信息架构 5 组（工单 73：14 项一级菜单 → 5 组，Miller 7±2 内）
 *
 * 组结构：概览 / 数据工厂 / 能力资产 / 运营管理 / 系统管理
 * 能力资产单入口：治理台七叶在 /capabilities（能力市场）；我的安装为租户叶。
 *
 * pageTitleFor：路由 → 顶部标题 的唯一派生源（消除 AdminLayout 内的 PAGE_TITLES 双源）。
 */
import React from 'react';
import {
  DashboardOutlined,
  BugOutlined,
  AppstoreOutlined,
  TeamOutlined,
  ToolOutlined,
} from '@ant-design/icons'

export interface MenuItem {
  key: string
  label: string
  icon?: React.ReactNode
  permission?: string // 访问该菜单所需的权限代码
  /** 租户视角页：端点要求租户 owner/admin（纯平台超管 tenant_id=NULL 不可入，菜单隐藏） */
  tenantOnly?: boolean
  /** 平台写叶：仅 is_platform_admin 可见；租户直打走 404 同形 */
  platformOnly?: boolean
  children?: MenuItem[]
}

/** 平台写面路由（导航隐藏 + 直打 404；与 /llm 无关） */
export const PLATFORM_WRITE_KEYS = ['/newapi', '/platform-ops', '/users'] as const

export const isPlatformWritePath = (pathname: string): boolean =>
  PLATFORM_WRITE_KEYS.some((p) => pathname === p || pathname.startsWith(`${p}/`))

/**
 * 完整菜单树定义（组 key 非路由，仅作折叠容器；叶子 key = 路由）
 */
export const menuConfig: MenuItem[] = [
  {
    key: '/overview',
    label: '概览',
    icon: React.createElement(DashboardOutlined),
    children: [
      { key: '/dashboard', label: '仪表盘', permission: 'menu:dashboard' },
      { key: '/usage', label: '用量看板', permission: 'menu:usage', tenantOnly: true },
      { key: '/relay', label: '渠道组', permission: 'menu:relay', tenantOnly: true },
    ],
  },
  {
    key: '/factory',
    label: '数据工厂',
    icon: React.createElement(BugOutlined),
    children: [
      { key: '/spiders/tasks', label: '采集任务', permission: 'menu:spiders.tasks' },
      { key: '/spiders/logs', label: '运行日志', permission: 'menu:spiders.logs' },
      { key: '/spiders/nodes', label: '节点监控', permission: 'menu:spiders.nodes' },
      { key: '/ai', label: 'AI 采集规划', permission: 'menu:ai' },
      { key: '/data', label: '数据中心', permission: 'menu:data' },
    ],
  },
  {
    key: '/assets',
    label: '能力资产',
    icon: React.createElement(AppstoreOutlined),
    children: [
      { key: '/capabilities', label: '能力市场', permission: 'menu:skills' },
      { key: '/capabilities/installs', label: '我的安装', permission: 'menu:skills', tenantOnly: true },
    ],
  },
  {
    key: '/ops',
    label: '运营管理',
    icon: React.createElement(TeamOutlined),
    children: [
      { key: '/members', label: '成员管理', permission: 'menu:members', tenantOnly: true },
      { key: '/platform-ops', label: '平台运营台', permission: 'menu:platform-ops', platformOnly: true },
      { key: '/logs', label: '日志中心', permission: 'menu:logs' },
    ],
  },
  {
    key: '/system',
    label: '系统管理',
    icon: React.createElement(ToolOutlined),
    children: [
      { key: '/llm', label: 'LLM 配置', permission: 'menu:llm' },
      { key: '/newapi', label: '中转站管控', permission: 'menu:newapi', platformOnly: true },
      { key: '/users', label: '用户管理', permission: 'menu:users', platformOnly: true },
      { key: '/settings', label: '系统设置', permission: 'menu:settings' },
    ],
  },
]

/**
 * 路由 → 页面标题（menuConfig 唯一派生，消双源）。
 * 叶子命中返回叶子 label；组路由返回组 label；兜底"后台管理"。
 */
export const pageTitleFor = (pathname: string): string => {
  for (const group of menuConfig) {
    if (group.key === pathname) return group.label
    const leaf = group.children?.find((c) => c.key === pathname)
    if (leaf) return leaf.label
  }
  return '后台管理'
}

/** DB 动态菜单 icon 标识 → 组件映射（/auth/menus 下发 icon 字符串经此渲染） */
export const MENU_ICON_MAP: Record<string, React.ReactNode> = {
  DashboardOutlined: React.createElement(DashboardOutlined),
  BugOutlined: React.createElement(BugOutlined),
  AppstoreOutlined: React.createElement(AppstoreOutlined),
  TeamOutlined: React.createElement(TeamOutlined),
  ToolOutlined: React.createElement(ToolOutlined),
}
