/**
 * 模块级导航注册（工单 66：401 导航改 navigate 保留 state.from）
 *
 * axios 拦截器在 Router 上下文之外，无法用 useNavigate hook；
 * App 挂载时注册 navigate 实现，未注册时兜底整页跳转。
 */
import type { NavigateFunction } from 'react-router-dom'

let navigateImpl: NavigateFunction | null = null

export const registerNavigate = (fn: NavigateFunction): void => {
  navigateImpl = fn
}

/** 跳登录页并携带来源路径（登录成功后可回跳；query `from` 只接受站内相对 path） */
export const navigateToLogin = (from?: string): void => {
  const raw = (from || '').trim()
  const safe =
    raw.startsWith('/') && !raw.startsWith('//') && !raw.includes('://') && !raw.includes('\\') && raw !== '/login'
      ? raw
      : ''
  const search = safe ? `?from=${encodeURIComponent(safe)}` : ''
  if (navigateImpl) {
    navigateImpl(`/login${search}`, { state: { from: safe || from, sessionExpired: true } })
  } else {
    window.location.href = `/login${search}`
  }
}
