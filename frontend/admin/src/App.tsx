import React, { Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom'
import { Spin } from 'antd'
import ProtectedRoute from './components/ProtectedRoute'
import AdminLayout from './components/AdminLayout'
import ErrorBoundary from './components/ErrorBoundary'
import { registerNavigate } from './services/navigation'
import { useAuthStore } from './store/useAuthStore'
import { isPlatformWritePath } from './config/menuConfig'

/**
 * 组织幽灵页（T-15 / GWT-82.3 / ADR-0021 决策 2）：不在 menuConfig 五组中。
 * 租户（含公司管理员）直打 = 缺页同形 404，不是「抱歉，您没有权限」；
 * /enterprise /rbac 本就是超管页——超管入口保持可达（ADR-0021 v2 和解句）。
 */
const ORG_GHOST_PATHS = ['/rbac', '/enterprise']

const isOrgGhostPath = (pathname: string): boolean =>
  ORG_GHOST_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`))

// 工单 69：19 页面全部 lazy——重依赖（recharts/代码编辑器等）按需分包，
// 首屏只载 AdminLayout + 当前路由 chunk
const Login = React.lazy(() => import('./pages/Login'))
const Dashboard = React.lazy(() => import('./pages/Dashboard'))
const Spiders = React.lazy(() => import('./pages/Spiders'))
const SpiderLogs = React.lazy(() => import('./pages/SpiderLogs'))
const Nodes = React.lazy(() => import('./pages/Nodes'))
const Users = React.lazy(() => import('./pages/Users'))
const Data = React.lazy(() => import('./pages/Data'))
const Settings = React.lazy(() => import('./pages/Settings'))
const AiPlans = React.lazy(() => import('./pages/AiPlans'))
const LlmProviders = React.lazy(() => import('./pages/LlmProviders'))
const NewApiOps = React.lazy(() => import('./pages/NewApiOps'))
const LogCenter = React.lazy(() => import('./pages/LogCenter'))
const Members = React.lazy(() => import('./pages/Members'))
const Usage = React.lazy(() => import('./pages/Usage'))
const Checkout = React.lazy(() => import('./pages/Checkout'))
const Pricing = React.lazy(() => import('./pages/Pricing'))
const Capabilities = React.lazy(() => import('./pages/Capabilities'))
const MyInstalls = React.lazy(() => import('./pages/MyInstalls'))
const PlatformOps = React.lazy(() => import('./pages/PlatformOps'))
const RelayGroups = React.lazy(() => import('./pages/RelayGroups'))
const OutboundKeys = React.lazy(() => import('./pages/OutboundKeys'))
const Unauthorized = React.lazy(() => import('./pages/Unauthorized'))
const NotFound = React.lazy(() => import('./pages/NotFound'))
const RbacManagement = React.lazy(() => import('./pages/RbacManagement'))
const EnterpriseManagement = React.lazy(() => import('./pages/EnterpriseManagement'))

const PageLoading = (
  <div style={{ display: 'flex', flexDirection: 'column', gap: 12, justifyContent: 'center', alignItems: 'center', minHeight: '60vh' }}>
    <Spin size="large" />
    <span style={{ color: '#888' }}>页面加载中…</span>
  </div>
)

// Router 上下文内注册 navigate，供 axios 401 拦截器使用（工单 66）
function NavigateRegistrar() {
  registerNavigate(useNavigate())
  return null
}

/** 路由级包装：Suspense + 错误边界（单页崩溃不拖垮整个工作台） */
function Page({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <ErrorBoundary label={label}>
      <Suspense fallback={PageLoading}>{children}</Suspense>
    </ErrorBoundary>
  )
}

/**
 * 主树唯一布局挂载点（T-29 / ADR-0022 单布局树，FR-96）：
 * 平台写面（/newapi /platform-ops /users）与业务页共用同一 AdminLayout——
 * 超管跨组切换命中同一路由分支，侧栏不卸载重挂、展开态保持、
 * 不再出现「权限加载中」（GWT-96.1/96.2；首访例外 GWT-96.3）。
 * 平台属性由本守卫表达：非超管（含未登录）直打平台写面或组织幽灵页
 * （/rbac /enterprise，T-15）= 缺页同形 404，不挂侧栏、不进 Unauthorized
 * （原 PlatformAdminLayout 语义保持，GWT-96.4 / GWT-82.3）。
 */
function MainLayout() {
  const { isAuthenticated, user } = useAuthStore()
  const location = useLocation()
  const platformOnly = isPlatformWritePath(location.pathname) || isOrgGhostPath(location.pathname)
  if (platformOnly && (!isAuthenticated || !user?.is_platform_admin)) {
    return <Page label="404"><NotFound /></Page>
  }
  return (
    <ProtectedRoute>
      <AdminLayout />
    </ProtectedRoute>
  )
}

function App() {
  return (
    <BrowserRouter>
      <NavigateRegistrar />
      <ErrorBoundary label="root">
        <Suspense fallback={PageLoading}>
          <Routes>
            <Route path="/login" element={<Page label="login"><Login /></Page>} />
            <Route path="/unauthorized" element={<Page label="unauthorized"><Unauthorized /></Page>} />

            <Route element={<MainLayout />}>
              <Route index element={<Navigate to="/dashboard" replace />} />
              <Route path="dashboard" element={<Page label="dashboard"><Dashboard /></Page>} />
              <Route path="spiders/tasks" element={<Page label="spiders"><Spiders /></Page>} />
              <Route path="spiders/logs" element={<Page label="spider-logs"><SpiderLogs /></Page>} />
              <Route path="spiders/nodes" element={<Page label="nodes"><Nodes /></Page>} />
              <Route path="ai" element={<Page label="ai"><AiPlans /></Page>} />
              {/* 组织幽灵页（T-15 / GWT-82.3）：守卫在 MainLayout 渲染前——租户=缺页同形 404，超管可达（ADR-0021 v2） */}
              <Route path="enterprise" element={<Page label="enterprise"><EnterpriseManagement /></Page>} />
              <Route path="rbac" element={<Page label="rbac"><RbacManagement /></Page>} />
              <Route path="capabilities/installs" element={<Page label="installs"><MyInstalls /></Page>} />
              <Route path="capabilities" element={<Page label="capabilities"><Capabilities /></Page>} />
              <Route path="members" element={<Page label="members"><Members /></Page>} />
              <Route path="usage" element={<Page label="usage"><Usage /></Page>} />
              <Route path="billing/checkout" element={<Page label="checkout"><Checkout /></Page>} />
              <Route path="pricing" element={<Page label="pricing"><Pricing /></Page>} />
              <Route path="relay" element={<Page label="relay"><RelayGroups /></Page>} />
              {/* T-06 出站拉数钥匙（FR-51）：数据工厂组叶，不冒充渠道组（X-KEY） */}
              <Route path="outbound-keys" element={<Page label="outbound-keys"><OutboundKeys /></Page>} />
              <Route path="llm" element={<Page label="llm"><LlmProviders /></Page>} />
              <Route path="logs" element={<Page label="logs"><LogCenter /></Page>} />
              <Route path="data" element={<Page label="data"><Data /></Page>} />
              {/* 平台写面并入主树（T-29 / ADR-0022）：同一布局挂载点，跨组切换不重挂 */}
              <Route path="newapi" element={<Page label="newapi"><NewApiOps /></Page>} />
              <Route path="platform-ops" element={<Page label="platform-ops"><PlatformOps /></Page>} />
              <Route path="users" element={<Page label="users"><Users /></Page>} />
              <Route
                path="settings"
                element={
                  <ProtectedRoute requireAdmin>
                    <Page label="settings"><Settings /></Page>
                  </ProtectedRoute>
                }
              />
            </Route>

            <Route path="*" element={<Page label="404"><NotFound /></Page>} />
          </Routes>
        </Suspense>
      </ErrorBoundary>
    </BrowserRouter>
  )
}

export default App
