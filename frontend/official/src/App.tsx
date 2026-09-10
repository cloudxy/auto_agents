import React, { Suspense } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ConfigProvider, Spin } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import SiteLayout from './components/layout/SiteLayout'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})

// 工单 70：页面 lazy 分包 + SiteLayout 统一壳 + 404 兜底
const Home = React.lazy(() => import('./pages/Home'))
const Capabilities = React.lazy(() => import('./pages/Capabilities'))
const CapabilityDetail = React.lazy(() => import('./pages/CapabilityDetail'))
const Register = React.lazy(() => import('./pages/Register'))
const Pricing = React.lazy(() => import('./pages/Pricing'))
const NotFound = React.lazy(() => import('./pages/NotFound'))

const PageLoading = (
  <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '50vh' }}>
    <Spin size="large" />
  </div>
)

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ConfigProvider locale={zhCN}>
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
                <Route path="*" element={<NotFound />} />
              </Route>
            </Routes>
          </Suspense>
        </BrowserRouter>
      </ConfigProvider>
    </QueryClientProvider>
  )
}

export default App
