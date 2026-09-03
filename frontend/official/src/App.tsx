import React, { Suspense } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { ConfigProvider, Spin } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import SiteLayout from './components/layout/SiteLayout'

// 工单 70：页面 lazy 分包 + SiteLayout 统一壳 + 404 兜底
const Home = React.lazy(() => import('./pages/Home'))
const SkillsSquare = React.lazy(() => import('./pages/SkillsSquare'))
const Capabilities = React.lazy(() => import('./pages/Capabilities'))
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
    <ConfigProvider locale={zhCN}>
      <BrowserRouter>
        <Suspense fallback={PageLoading}>
          <Routes>
            <Route element={<SiteLayout />}>
              <Route path="/" element={<Home />} />
              <Route path="/skills" element={<SkillsSquare />} />
              <Route path="/capabilities" element={<Capabilities />} />
              <Route path="/register" element={<Register />} />
              <Route path="/pricing" element={<Pricing />} />
              <Route path="*" element={<NotFound />} />
            </Route>
          </Routes>
        </Suspense>
      </BrowserRouter>
    </ConfigProvider>
  )
}

export default App
