/**
 * 后台管理布局 - 包含侧边栏、顶部导航和内容区
 *
 * 侧栏单一真相（T-15 / ADR-0021）：唯一输入 = menuConfig 经 usePermission
 * 权限过滤（filteredMenus）。/auth/menus 动态树不再驱动侧栏（RBAC 页仍可
 * 读该接口）——脏 DB 菜单树不影响租户看见哪几片叶（GWT-82.1）。
 *
 * 窄屏（< lg，审计 BUG-39 / B5-6，D33 抽屉化）：侧栏收成 0 宽，顶栏左侧出现菜单按钮，
 * 点开是同一份菜单的抽屉；页级 tab 从顶栏移到内容区顶部；欢迎语隐藏、页名省略号。
 * 侧栏节点始终挂载（ADR-0022 单布局树：切页不重挂侧栏）。
 */
import React, { useMemo, useState } from 'react'
import { Layout, Menu, Button, Tabs, Tag, Drawer } from 'antd'
import { MenuOutlined, RocketOutlined } from '@ant-design/icons'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '../store/useAuthStore'
import { usePermission } from '../hooks/usePermission'
import { pageTitleFor } from '../config/menuConfig'
import { PageHeaderSlotContext, type PageHeaderTabBar } from './layout/PageHeaderTabs'
import { tenantRoleLabel } from '../constants/roles'

const { Header, Sider, Content } = Layout

const Brand: React.FC = () => (
  <div className="admin-brand">
    <span className="brand-mark" aria-hidden><RocketOutlined /></span>
    AutoAgents
  </div>
)

const AdminLayout: React.FC = () => {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuthStore()
  const { filteredMenus, permissionsReady, permissionsLoadState } = usePermission()
  const [isNarrow, setIsNarrow] = useState(false)
  const [navOpen, setNavOpen] = useState(false)

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

  const roleLabel = user?.is_platform_admin
    ? null
    : user?.tenant_role
      ? tenantRoleLabel(user.tenant_role)
      : user?.role || null

  const permissionHint = !permissionsReady ? (
    <div style={{ color: 'rgba(255,255,255,0.65)', padding: '8px 20px', fontSize: 12 }}>
      {permissionsLoadState === 'error' ? '权限暂时刷新失败，已保留上次菜单。' : '权限加载中'}
    </div>
  ) : null

  const renderMenu = (onNavigate?: () => void) => (
    <Menu
      theme="dark"
      mode="inline"
      selectedKeys={[location.pathname]}
      items={menuItems}
      onClick={({ key }) => { navigate(key); onNavigate?.() }}
      style={{ borderInlineEnd: 0 }}
    />
  )

  const pageTabs = pageTabBar ? (
    <Tabs
      items={pageTabBar.items}
      activeKey={pageTabBar.activeKey}
      onChange={pageTabBar.onChange}
    />
  ) : null

  return (
    <PageHeaderSlotContext.Provider value={pageHeaderSlot}>
      <Layout style={{ minHeight: '100vh' }}>
        <Sider
          theme="dark"
          width={220}
          breakpoint="lg"
          collapsedWidth={0}
          trigger={null}
          onBreakpoint={(broken) => { setIsNarrow(broken); if (!broken) setNavOpen(false) }}
          style={{ position: 'sticky', top: 0, height: '100vh', overflowY: 'auto' }}
        >
          <Brand />
          {permissionHint}
          {renderMenu()}
        </Sider>
        {isNarrow && (
          <Drawer
            placement="left"
            open={navOpen}
            onClose={() => setNavOpen(false)}
            size={260}
            closable={false}
            styles={{ body: { padding: 0, background: 'var(--color-deep-space)' } }}
          >
            <Brand />
            {permissionHint}
            {renderMenu(() => setNavOpen(false))}
          </Drawer>
        )}
        <Layout className="admin-main">
          {/* §0.10 页头 token：顶栏行高 56、页名 16/600（唯一标题）、页名↔页级 tab 间距 16 */}
          <Header
            className="admin-header"
            style={{ background: '#fff', padding: '0 24px', height: 56, lineHeight: '56px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', boxShadow: '0 1px 4px rgba(0,21,41,0.08)' }}
          >
            <div style={{ display: 'flex', alignItems: 'center', minWidth: 0, gap: 8 }}>
              {isNarrow && (
                <Button type="text" icon={<MenuOutlined />} aria-label="打开菜单" onClick={() => setNavOpen(true)} />
              )}
              <div className="admin-header-title">
                {pageTitleFor(location.pathname)}
              </div>
              {pageTabBar && !isNarrow && (
                <div className="page-header-tabs" style={{ marginLeft: 8, minWidth: 0 }}>
                  {pageTabs}
                </div>
              )}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', flex: 'none' }}>
              <span className="admin-header-welcome" style={{ marginRight: 8 }}>
                欢迎回来，<strong>{user?.username || '用户'}</strong>
                {user?.is_platform_admin
                  ? <Tag color="gold" style={{ marginLeft: 8 }}>平台超管</Tag>
                  : roleLabel
                    ? <Tag style={{ marginLeft: 8 }}>{roleLabel}</Tag>
                    : null}
              </span>
              <Button type="link" onClick={() => { logout(); navigate('/login') }}>退出登录</Button>
            </div>
          </Header>
          <Content className="admin-content">
            {pageTabBar && isNarrow && <div style={{ marginTop: -8 }}>{pageTabs}</div>}
            <Outlet />
          </Content>
        </Layout>
      </Layout>
    </PageHeaderSlotContext.Provider>
  )
}

export default AdminLayout
