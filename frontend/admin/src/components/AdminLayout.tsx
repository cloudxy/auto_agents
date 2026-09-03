/**
 * 后台管理布局 - 包含侧边栏、顶部导航和内容区
 */
import React, { useMemo } from 'react'
import { Layout, Menu, Typography, Button } from 'antd'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '../store/useAuthStore'
import { usePermission } from '../hooks/usePermission'
import { pageTitleFor, MENU_ICON_MAP } from '../config/menuConfig'
import { useQuery } from '@tanstack/react-query'
import { fetchDynamicMenus, type DynamicMenuNode } from '../services/menus'

const { Header, Sider, Content } = Layout
const { Title } = Typography

const AdminLayout: React.FC = () => {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuthStore()
  const { filteredMenus } = usePermission()

  // 动态菜单（SaaS 化：menus 表经 /auth/menus 下发，按权限已过滤）；
  // 空响应/失败回退前端静态 menuConfig（登录链路永不因菜单故障阻断）
  const { data: dynamicMenus } = useQuery({
    queryKey: ['dynamic-menus'],
    queryFn: fetchDynamicMenus,
    staleTime: 60_000,
  })

  const menuItems = useMemo(() => {
    if (dynamicMenus && dynamicMenus.length) {
      // 平台超管（无租户）隐藏租户视角菜单
      const tenantBound = user?.tenant_id != null
      const toItems = (nodes: DynamicMenuNode[]): any[] => nodes
        .filter((n) => !n.tenantOnly || tenantBound)
        .map((n) => ({
          key: n.key,
          icon: n.icon ? MENU_ICON_MAP[n.icon] : undefined,
          label: n.label,
          children: n.children?.length ? toItems(n.children) : undefined,
        }))
      return toItems(dynamicMenus)
    }
    return filteredMenus.map(item => ({
      key: item.key,
      icon: item.icon,
      label: item.label,
      children: item.children?.map(child => ({
        key: child.key,
        label: child.label
      }))
    }))
  }, [dynamicMenus, filteredMenus, user?.tenant_id])

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
            {pageTitleFor(location.pathname)}
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
