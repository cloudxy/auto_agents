import React, { Suspense } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ConfigProvider, Spin } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { BRAND_TOKENS } from '@auto-agents/frontend-shared'
import SiteLayout from './components/layout/SiteLayout'
// antd 反馈（message）走 App 实例，吃到 ConfigProvider 的中文文案与主题
import { FeedbackProvider } from './feedback'

// 工单 78：react-query 全局客户端（轮询/缓存/失焦暂停统一托管），全应用唯一一份
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})

// 工单 77（D7）：语义色单源（shared BRAND_TOKENS），与 admin 同口径——品牌换色只改 shared
const THEME = {
  token: {
    colorPrimary: BRAND_TOKENS.primary,
    colorSuccess: BRAND_TOKENS.success,
    colorWarning: BRAND_TOKENS.warning,
    colorError: BRAND_TOKENS.danger,
    colorInfo: BRAND_TOKENS.primary,
  },
}

// 工单 70：页面 lazy 分包 + SiteLayout 统一壳 + 404 兜底
const Home = React.lazy(() => import('./pages/Home'))
const Capabilities = React.lazy(() => import('./pages/Capabilities'))
const CapabilityDetail = React.lazy(() => import('./pages/CapabilityDetail'))
const Register = React.lazy(() => import('./pages/Register'))
const Pricing = React.lazy(() => import('./pages/Pricing'))
const Legal = React.lazy(() => import('./pages/Legal'))
const NotFound = React.lazy(() => import('./pages/NotFound'))

const PageLoading = (
  <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '50vh' }}>
    <Spin size="large" />
  </div>
)

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ConfigProvider locale={zhCN} theme={THEME}>
        <FeedbackProvider>
          <BrowserRouter>
            <Suspense fallback={PageLoading}>
              <Routes>
                <Route element={<SiteLayout />}>
                  <Route path="/" element={<Home />} />
                  <Route path="/skills" element={<Capabilities />} />
                  <Route path="/capabilities/:type/:slug" element={<CapabilityDetail />} />
                  <Route path="/capabilities" element={<Capabilities />} />
                  <Route path="/register" element={<Register />} />
                  <Route path="/pricing" element={<Pricing />} />
                  <Route path="/terms" element={<Legal />} />
                  <Route path="/privacy" element={<Legal />} />
                  <Route path="*" element={<NotFound />} />
                </Route>
              </Routes>
            </Suspense>
          </BrowserRouter>
        </FeedbackProvider>
      </ConfigProvider>
    </QueryClientProvider>
  )
}

export default App
