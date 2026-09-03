/**
 * Axios 实例（工单 66：client 由 shared createApiClient 工厂创建）
 *
 * 官网无鉴权：只传 baseURL，调 /public/* 端点。
 */
import { createApiClient } from '@auto-agents/frontend-shared'

const api = createApiClient({
  baseURL: process.env.REACT_APP_API_BASE_URL || 'http://localhost:9111/api/v1',
})

export default api

// 信封解包单源在 shared（F-6），经此再导出供 service 层使用
export { unwrap } from '@auto-agents/frontend-shared'
