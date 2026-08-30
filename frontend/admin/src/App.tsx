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
          <Route path="llm" element={<LlmProviders />} />
          <Route path="newapi" element={<NewApiOps />} />
          <Route path="logs" element={<LogCenter />} />
          <Route path="users" element={<Users />} />
          <Route path="data" element={<Data />} />
          <Route path="settings" element={<Settings />} />
        </Route>

        {/* 未匹配路由兼底 */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
