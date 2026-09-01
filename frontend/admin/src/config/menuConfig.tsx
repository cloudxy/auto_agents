/**
 * 菜单配置 - 定义系统所有菜单项及其权限要求
 */
import React from 'react';
import {
  DashboardOutlined,
  BugOutlined,
  UserOutlined,
  SettingOutlined,
  DatabaseOutlined,
  RobotOutlined,
  FileTextOutlined,
  ApiOutlined,
  CloudServerOutlined
} from '@ant-design/icons'

export interface MenuItem {
  key: string
  label: string
  icon?: React.ReactNode
  permission?: string // 访问该菜单所需的权限代码
  children?: MenuItem[]
}

/**
 * 完整菜单树定义
 */
export const menuConfig: MenuItem[] = [
  {
    key: '/dashboard',
    label: '仪表盘',
    icon: React.createElement(DashboardOutlined),
    permission: 'menu:dashboard'
  },
  {
    key: '/spiders',
    label: '爬虫管理',
    icon: React.createElement(BugOutlined),
    permission: 'menu:spiders',
    children: [
      { key: '/spiders/tasks', label: '任务列表', permission: 'menu:spiders.tasks' },
      { key: '/spiders/logs', label: '运行日志', permission: 'menu:spiders.logs' },
      { key: '/spiders/nodes', label: '节点', permission: 'menu:spiders.nodes' }
    ]
  },
  {
    key: '/ai',
    label: 'AI 采集',
    icon: React.createElement(RobotOutlined),
    permission: 'menu:ai'
  },
  {
    key: '/skills',
    label: '技能中心',
    icon: React.createElement(FileTextOutlined),
    permission: 'menu:skills'
  },
  {
    key: '/members',
    label: '成员管理',
    icon: React.createElement(UserOutlined),
    permission: 'menu:members'
  },
  {
    key: '/usage',
    label: '用量看板',
    icon: React.createElement(DashboardOutlined),
    permission: 'menu:usage'
  },
  {
    key: '/llm',
    label: 'LLM 配置',
    icon: React.createElement(ApiOutlined),
    permission: 'menu:llm'
  },
  {
    key: '/newapi',
    label: '中转站',
    icon: React.createElement(CloudServerOutlined),
    permission: 'menu:newapi'
  },
  {
    key: '/logs',
    label: '日志中心',
    icon: React.createElement(FileTextOutlined),
    permission: 'menu:logs'
  },
  {
    key: '/users',
    label: '用户管理',
    icon: React.createElement(UserOutlined),
    permission: 'menu:users'
  },
  {
    key: '/data',
    label: '数据中心',
    icon: React.createElement(DatabaseOutlined),
    permission: 'menu:data'
  },
  {
    key: '/settings',
    label: '系统设置',
    icon: React.createElement(SettingOutlined),
    permission: 'menu:settings'
  }
]
