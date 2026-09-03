import React, { Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import { Spin } from 'antd'
import ProtectedRoute from './components/ProtectedRoute'
import AdminLayout from './components/AdminLayout'
import ErrorBoundary from './components/ErrorBoundary'
import { registerNavigate } from './services/navigation'

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
const Capabilities = React.lazy(() => import('./pages/Capabilities'))
const PlatformOps = React.lazy(() => import('./pages/PlatformOps'))
const Unauthorized = React.lazy(() => import('./pages/Unauthorized'))
const NotFound = React.lazy(() => import('./pages/NotFound'))
const RbacManagement = React.lazy(() => import('./pages/RbacManagement'))

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

function App() {
  return (
    <BrowserRouter>
      <NavigateRegistrar />
      <ErrorBoundary label="root">
        <Suspense fallback={PageLoading}>
          <Routes>
            {/* 公开路由 */}
            <Route path="/login" element={<Page label="login"><Login /></Page>} />
            <Route path="/unauthorized" element={<Page label="unauthorized"><Unauthorized /></Page>} />

            {/* 受保护路由 - 使用 Layout */}
            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <AdminLayout />
                </ProtectedRoute>
              }
            >
              <Route index element={<Navigate to="/dashboard" replace />} />
              <Route path="dashboard" element={<Page label="dashboard"><Dashboard /></Page>} />
              <Route path="spiders/tasks" element={<Page label="spiders"><Spiders /></Page>} />
              <Route path="spiders/logs" element={<Page label="spider-logs"><SpiderLogs /></Page>} />
              <Route path="spiders/nodes" element={<Page label="nodes"><Nodes /></Page>} />
              <Route path="ai" element={<Page label="ai"><AiPlans /></Page>} />
              <Route
                path="rbac"
                element={
                  <ProtectedRoute requireAdmin>
                    <Page label="rbac"><RbacManagement /></Page>
                  </ProtectedRoute>
                }
              />
              {/* 能力资产单入口（工单 73）：技能 Tab 内嵌 Skills 组件，权限由其内部 usePermission 控制 */}
              <Route path="capabilities" element={<Page label="capabilities"><Capabilities /></Page>} />
              {/* 成员管理（SaaS S2）：租户内部事务，owner/admin 语义在页内守卫 */}
              <Route path="members" element={<Page label="members"><Members /></Page>} />
              <Route path="usage" element={<Page label="usage"><Usage /></Page>} />
              {/* 平台运营为 admin 专属：菜单隐藏只是视觉，直达 URL 必须拦截（工单 69 修复） */}
              <Route
                path="platform-ops"
                element={
                  <ProtectedRoute requireAdmin>
                    <Page label="platform-ops"><PlatformOps /></Page>
                  </ProtectedRoute>
                }
              />
              {/* UX-B4：路由级权限守卫——admin 专属页面（LLM 配置/中转站/用户/设置） */}
              <Route
                path="llm"
                element={
                  <ProtectedRoute requireAdmin>
                    <Page label="llm"><LlmProviders /></Page>
                  </ProtectedRoute>
                }
              />
              <Route
                path="newapi"
                element={
                  <ProtectedRoute requireAdmin>
                    <Page label="newapi"><NewApiOps /></Page>
                  </ProtectedRoute>
                }
              />
              <Route path="logs" element={<Page label="logs"><LogCenter /></Page>} />
              <Route
                path="users"
                element={
                  <ProtectedRoute requireAdmin>
                    <Page label="users"><Users /></Page>
                  </ProtectedRoute>
                }
              />
              <Route path="data" element={<Page label="data"><Data /></Page>} />
              <Route
                path="settings"
                element={
                  <ProtectedRoute requireAdmin>
                    <Page label="settings"><Settings /></Page>
                  </ProtectedRoute>
                }
              />
              {/* 布局内未匹配 → 404（保持导航可用） */}
              <Route path="*" element={<Page label="404"><NotFound /></Page>} />
            </Route>

            {/* 布局外未匹配（如匿名访问未知路径）→ 404 */}
            <Route path="*" element={<Page label="404"><NotFound /></Page>} />
          </Routes>
        </Suspense>
      </ErrorBoundary>
    </BrowserRouter>
  )
}

export default App
