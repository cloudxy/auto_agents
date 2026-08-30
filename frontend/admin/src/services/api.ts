/**
 * Axios 实例配置（Token 统一从 auth store 读取，避免与登录写入路径不一致）
 */
import axios from 'axios'
import { useAuthStore } from '../store/useAuthStore'

const api = axios.create({
  baseURL: process.env.REACT_APP_API_BASE_URL || 'http://localhost:9111/api/v1',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 请求拦截器
api.interceptors.request.use(
  (config) => {
    const token = useAuthStore.getState().token
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器
api.interceptors.response.use(
  (response) => {
    return response.data
  },
  (error) => {
    if (error.response?.status === 401) {
      // Token 过期，清空登录态并跳转登录页
      useAuthStore.getState().logout()
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

/**
 * 统一响应信封（与后端 ApiResponse / PaginatedResponse 对齐，ADR-001）
 * 拦截器已剥掉 axios 层的 response，这里拿到的是整个信封体，
 * 业务载荷在 data 字段。
 */
export interface ApiEnvelope<T> {
  success: boolean
  code: string
  message: string
  data: T
  request_id?: string | null
}

/** 从信封中解出业务载荷（service 层统一出口） */
export const unwrap = <T,>(envelope: unknown): T =>
  (envelope as ApiEnvelope<T>).data

export default api
