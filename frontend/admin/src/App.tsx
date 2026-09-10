import React, { Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import { Spin } from 'antd'
import ProtectedRoute from './components/ProtectedRoute'
import AdminLayout from './components/AdminLayout'
import ErrorBoundary from './components/ErrorBoundary'
import { registerNavigate } from './services/navigation'
import { useAuthStore } from './store/useAuthStore'

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
const MyInstalls = React.lazy(() => import('./pages/MyInstalls'))
const PlatformOps = React.lazy(() => import('./pages/PlatformOps'))
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

/** 平台写面布局：非超管（含未登录）与缺页同一 NotFound，不进 Unauthorized */
function PlatformAdminLayout() {
  const { isAuthenticated, user } = useAuthStore()
  if (!isAuthenticated || !user?.is_platform_admin) {
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

            <Route element={<PlatformAdminLayout />}>
              <Route path="newapi" element={<Page label="newapi"><NewApiOps /></Page>} />
              <Route path="platform-ops" element={<Page label="platform-ops"><PlatformOps /></Page>} />
              <Route path="users" element={<Page label="users"><Users /></Page>} />
            </Route>

            <Route
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
                path="enterprise"
                element={
                  <ProtectedRoute requireAdmin>
                    <Page label="enterprise"><EnterpriseManagement /></Page>
                  </ProtectedRoute>
                }
              />
              <Route
                path="rbac"
                element={
                  <ProtectedRoute requireAdmin>
                    <Page label="rbac"><RbacManagement /></Page>
                  </ProtectedRoute>
                }
              />
              <Route path="capabilities/installs" element={<Page label="installs"><MyInstalls /></Page>} />
              <Route path="capabilities" element={<Page label="capabilities"><Capabilities /></Page>} />
              <Route path="members" element={<Page label="members"><Members /></Page>} />
              <Route path="usage" element={<Page label="usage"><Usage /></Page>} />
              <Route path="llm" element={<Page label="llm"><LlmProviders /></Page>} />
              <Route path="logs" element={<Page label="logs"><LogCenter /></Page>} />
              <Route path="data" element={<Page label="data"><Data /></Page>} />
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
