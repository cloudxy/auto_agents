/**
 * 认证服务
 */
import api from './api'

export interface LoginParams {
  username: string
  password: string
  remember_me?: boolean // 记住我
}

export interface LoginResponse {
  access_token: string
  token_type: string
  username: string
  is_admin: boolean
  role?: 'admin' | 'operator' | 'viewer' | string
}

/**
 * 统一响应信封（与后端 ApiResponse 对齐）
 */
interface ApiEnvelope<T> {
  success: boolean
  code: string
  message: string
  data: T
  request_id?: string | null
}

/**
 * 用户登录（后端用 ApiResponse 包装，需解包 data）
 */
export const login = (params: LoginParams): Promise<LoginResponse> => {
  return api.post('/auth/login', params)
    .then((res) => (res as unknown as ApiEnvelope<LoginResponse>).data)
}

/**
 * 用户注册
 */
export const register = (username: string, email: string, password: string) => {
  return api.post('/auth/register', null, {
    params: { username, email, password }
  })
}
