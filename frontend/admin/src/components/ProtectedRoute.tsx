/**
 * 路由守卫 - 保护需要登录的页面（认证状态以 useAuthStore 为唯一源）
 *
 * requireAdmin：租户公司管理员可入。`/llm` 经办可进（SH-11，不再包 requireAdmin）。
 * requirePlatformAdmin：非超管渲染与未登录缺页相同的 NotFound（GWT-07.3）。
 */
import React from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '../store/useAuthStore'
import NotFound from '../pages/NotFound'

interface ProtectedRouteProps {
  children: React.ReactNode
  requireAdmin?: boolean
  requirePlatformAdmin?: boolean
}

const ProtectedRoute: React.FC<ProtectedRouteProps> = ({
  children,
  requireAdmin = false,
  requirePlatformAdmin = false,
}) => {
  const { isAuthenticated, user } = useAuthStore()
  const location = useLocation()

  if (!isAuthenticated) {
    if (requirePlatformAdmin) return <NotFound />
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  if (requirePlatformAdmin && !user?.is_platform_admin) {
    return <NotFound />
  }

  if (requireAdmin && user?.role !== 'admin' && !user?.is_admin) {
    return <Navigate to="/unauthorized" replace />
  }

  return <>{children}</>
}

export default ProtectedRoute
