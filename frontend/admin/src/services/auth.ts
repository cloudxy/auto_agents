/**
 * 认证服务
 */
import api, { unwrap, type ApiEnvelope } from './api'

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
  /** 租户维度（与 JWT 同源）：租户视角菜单可见性判定（NULL=纯平台超管） */
  tenant_id?: number | null
  tenant_role?: string | null
}


/**
 * 用户登录（后端用 ApiResponse 包装，需解包 data）
 */
export const login = (params: LoginParams): Promise<LoginResponse> => {
  return api.post('/auth/login', params)
    .then((res) => unwrap<LoginResponse>(res))
}

/**
 * 用户注册（P1-3 修复：后端期望 JSON body——旧实现把密码放 URL query
 * 且 body 为 null，必然 422，且密码会进各级访问日志）
 */
export const register = (username: string, email: string, password: string) => {
  return api.post('/auth/register', { username, email, password })
}
