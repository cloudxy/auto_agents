/**
 * Axios 实例（工单 66：client 由 shared createApiClient 工厂创建）
 *
 * Token 从 auth store 读取；401 清登录态并 navigate('/login', {state:{from}})
 * 替代原 window.location.href（保留来源路径，登录后可回跳）。
 */
import { createApiClient } from '@auto-agents/frontend-shared'
import { useAuthStore } from '../store/useAuthStore'
import { navigateToLogin } from './navigation'

const api = createApiClient({
  baseURL: process.env.REACT_APP_API_BASE_URL || 'http://localhost:9111/api/v1',
  getAuthToken: () => useAuthStore.getState().token,
  onUnauthorized: () => {
    useAuthStore.getState().logout()
    navigateToLogin(window.location.pathname)
  },
})

// 信封类型单源在 shared（F-6），此处仅再导出供存量 import 兼容
export { unwrap } from '@auto-agents/frontend-shared'
export type { ApiEnvelope } from '@auto-agents/frontend-shared'

export default api
