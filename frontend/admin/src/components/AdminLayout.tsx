/**
 * 后台管理布局 - 包含侧边栏、顶部导航和内容区
 *
 * 侧栏单一真相（T-15 / ADR-0021）：唯一输入 = menuConfig 经 usePermission
 * 权限过滤（filteredMenus）。/auth/menus 动态树不再驱动侧栏（RBAC 页仍可
 * 读该接口）——脏 DB 菜单树不影响租户看见哪几片叶（GWT-82.1）。
 */
import React, { useMemo, useState } from 'react'
import { Layout, Menu, Typography, Button, Tabs, Tag } from 'antd'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '../store/useAuthStore'
import { usePermission } from '../hooks/usePermission'
import { pageTitleFor } from '../config/menuConfig'
import { PageHeaderSlotContext, type PageHeaderTabBar } from './layout/PageHeaderTabs'

const { Header, Sider, Content } = Layout
const { Title } = Typography

const AdminLayout: React.FC = () => {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuthStore()
  const { filteredMenus, permissionsReady, permissionsLoadState } = usePermission()

  // 页级 tab 槽位（T-31 / FR-99 §0.10）：页面经 PageHeaderTabs 注册到顶栏行
  const [pageTabBar, setPageTabBar] = useState<PageHeaderTabBar | null>(null)
  const pageHeaderSlot = useMemo(() => ({ setTabBar: setPageTabBar }), [])

  const menuItems = useMemo(() => filteredMenus.map(item => ({
    key: item.key,
    icon: item.icon,
    label: item.label,
    children: item.children?.map(child => ({
      key: child.key,
      label: child.label
    }))
  })), [filteredMenus])

  return (
    <PageHeaderSlotContext.Provider value={pageHeaderSlot}>
      <Layout style={{ minHeight: '100vh' }}>
        <Sider theme="dark">
          <div style={{ height: 64, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Title level={4} style={{ color: 'white', margin: 0 }}>AutoAgents</Title>
          </div>
          {!permissionsReady && (
            <div style={{ color: 'rgba(255,255,255,0.65)', padding: '8px 16px', fontSize: 12 }}>
              {permissionsLoadState === 'error' ? '权限暂时刷新失败，已保留上次菜单。' : '权限加载中'}
            </div>
          )}
          <Menu
            theme="dark"
            mode="inline"
            selectedKeys={[location.pathname]}
            items={menuItems}
            onClick={({ key }) => navigate(key)}
          />
        </Sider>
        <Layout>
          {/* §0.10 页头 token：顶栏行高 56、页名 16/600（唯一标题）、页名↔页级 tab 间距 16 */}
          <Header style={{ background: '#fff', padding: '0 24px', height: 56, lineHeight: '56px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', boxShadow: '0 1px 4px rgba(0,21,41,0.08)' }}>
            <div style={{ display: 'flex', alignItems: 'center', minWidth: 0 }}>
              <div style={{ fontSize: 16, fontWeight: 600 }}>
                {pageTitleFor(location.pathname)}
              </div>
              {pageTabBar && (
                <div className="page-header-tabs" style={{ marginLeft: 16 }}>
                  <Tabs
                    items={pageTabBar.items}
                    activeKey={pageTabBar.activeKey}
                    onChange={pageTabBar.onChange}
                  />
                </div>
              )}
            </div>
            <div style={{ display: 'flex', alignItems: 'center' }}>
              <span style={{ marginRight: 16 }}>
                欢迎回来，<strong>{user?.username || '用户'}</strong>
                {user?.is_platform_admin
                  ? <Tag color="gold" style={{ marginLeft: 8 }}>平台超管</Tag>
                  : user?.tenant_role
                    ? <Tag style={{ marginLeft: 8 }}>{user.tenant_role}{user.tenant_id != null ? ` · 租户 ${user.tenant_id}` : ''}</Tag>
                    : user?.role
                      ? <Tag style={{ marginLeft: 8 }}>{user.role}</Tag>
                      : null}
              </span>
              <Button type="link" onClick={() => { logout(); navigate('/login') }}>退出登录</Button>
            </div>
          </Header>
          {/* §0.10 内容区 token（T-34 铺页批）：顶栏下沿→内容首行 16px；
              区块间 16px 由各页 marginBottom/marginTop 承担（content.block-gap） */}
          <Content style={{ margin: '16px 16px 24px', padding: '0 24px 24px', background: '#fff', minHeight: 280 }}>
            <Outlet />
          </Content>
        </Layout>
      </Layout>
    </PageHeaderSlotContext.Provider>
  )
}

export default AdminLayout
