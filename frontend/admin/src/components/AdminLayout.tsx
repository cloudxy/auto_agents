/**
 * 后台管理布局 - 包含侧边栏、顶部导航和内容区
 */
import React from 'react'
import { Layout, Menu, Typography, Button } from 'antd'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '../store/useAuthStore'
import { usePermission } from '../hooks/usePermission'

const { Header, Sider, Content } = Layout
const { Title } = Typography

// 路由 → 顶部标题映射
const PAGE_TITLES: Record<string, string> = {
  '/dashboard': '控制面板',
  '/settings': '系统设置',
  '/spiders/tasks': '任务管理',
  '/spiders/logs': '运行日志',
  '/spiders/nodes': '节点监控',
  '/ai': 'AI 采集',
  '/llm': 'LLM 配置',
  '/newapi': '中转站管控',
  '/logs': '日志中心',
  '/users': '用户管理',
  '/data': '数据中心',
}

const AdminLayout: React.FC = () => {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuthStore()
  const { filteredMenus } = usePermission()

  // 将菜单配置转换为 Ant Design Menu 组件所需的格式
  const menuItems = filteredMenus.map(item => ({
    key: item.key,
    icon: item.icon,
    label: item.label,
    children: item.children?.map(child => ({
      key: child.key,
      label: child.label
    }))
  }))

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider theme="dark">
        <div style={{ height: 64, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Title level={4} style={{ color: 'white', margin: 0 }}>AutoAgents</Title>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header style={{ background: '#fff', padding: '0 24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', boxShadow: '0 1px 4px rgba(0,21,41,0.08)' }}>
          <div style={{ fontSize: '18px', fontWeight: 500 }}>
            {PAGE_TITLES[location.pathname] || '后台管理'}
          </div>
          <div style={{ display: 'flex', alignItems: 'center' }}>
            <span style={{ marginRight: '16px' }}>欢迎回来，<strong>{user?.username || '用户'}</strong></span>
            <Button type="link" onClick={() => { logout(); navigate('/login') }}>退出登录</Button>
          </div>
        </Header>
        <Content style={{ margin: '24px 16px', padding: 24, background: '#fff', minHeight: 280 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}

export default AdminLayout
