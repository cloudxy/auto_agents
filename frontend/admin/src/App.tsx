import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import ProtectedRoute from './components/ProtectedRoute'
import AdminLayout from './components/AdminLayout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Spiders from './pages/Spiders'
import SpiderLogs from './pages/SpiderLogs'
import Nodes from './pages/Nodes'
import Users from './pages/Users'
import Data from './pages/Data'
import Settings from './pages/Settings'
import AiPlans from './pages/AiPlans'
import LlmProviders from './pages/LlmProviders'
import NewApiOps from './pages/NewApiOps'
import LogCenter from './pages/LogCenter'
import Skills from './pages/Skills'
import Unauthorized from './pages/Unauthorized'
import './App.css'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* 公开路由 */}
        <Route path="/login" element={<Login />} />
        <Route path="/unauthorized" element={<Unauthorized />} />

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
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="spiders/tasks" element={<Spiders />} />
          <Route path="spiders/logs" element={<SpiderLogs />} />
          <Route path="spiders/nodes" element={<Nodes />} />
          <Route path="ai" element={<AiPlans />} />
          {/* 技能中心（方案 A）：三角色可见（viewer 只读），写操作由按钮级权限控制 */}
          <Route path="skills" element={<Skills />} />
          {/* UX-B4：路由级权限守卫——admin 专属页面（LLM 配置/中转站/用户/设置）
              菜单隐藏只是视觉隐藏，直达 URL 必须被拦截到 /unauthorized */}
          <Route
            path="llm"
            element={
              <ProtectedRoute requireAdmin>
                <LlmProviders />
              </ProtectedRoute>
            }
          />
          <Route
            path="newapi"
            element={
              <ProtectedRoute requireAdmin>
                <NewApiOps />
              </ProtectedRoute>
            }
          />
          <Route path="logs" element={<LogCenter />} />
          <Route
            path="users"
            element={
              <ProtectedRoute requireAdmin>
                <Users />
              </ProtectedRoute>
            }
          />
          <Route path="data" element={<Data />} />
          <Route
            path="settings"
            element={
              <ProtectedRoute requireAdmin>
                <Settings />
              </ProtectedRoute>
            }
          />
        </Route>

        {/* 未匹配路由兼底 */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
