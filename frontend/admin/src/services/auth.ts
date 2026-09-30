/**
 * 认证服务
 */
import api, { unwrap } from './api'

export interface LoginParams {
  username: string
  password: string
  remember_me?: boolean // 记住我
}

export interface LoginResponse {
  access_token: string
  /** 刷新令牌与访问令牌有效秒数（决策 D10） */
  refresh_token?: string
  expires_in?: number
  /** 决策 D21：企业负责人待验证邮箱（验证前不能用 AI 规划） */
  email_verify_pending?: boolean
  token_type: string
  username: string
  is_admin: boolean
  role?: 'admin' | 'operator' | 'viewer' | string
  /** 租户维度（与 JWT 同源）：租户视角菜单可见性判定（NULL=纯平台超管） */
  tenant_id?: number | null
  tenant_role?: string | null
  /** 平台超管；缺省/旧客户端当 false（T-05 投影） */
  is_platform_admin?: boolean
}


/**
 * 用户登录（后端用 ApiResponse 包装，需解包 data）
 */
export const login = (params: LoginParams): Promise<LoginResponse> => {
  return api.post('/auth/login', params)
    .then((res) => unwrap<LoginResponse>(res))
}

/** 用刷新令牌换一对新令牌（决策 D10；由 api 客户端在 401 时静默调用） */
export const refreshSessionTokens = (refreshToken: string): Promise<{ access_token: string; refresh_token: string }> =>
  api.post('/auth/refresh', { refresh_token: refreshToken })
    .then((res) => unwrap<{ access_token: string; refresh_token: string }>(res))

/** 登出：作废本会话的刷新令牌 */
export const logoutSession = (refreshToken: string): Promise<void> =>
  api.post('/auth/logout', { refresh_token: refreshToken }).then(() => undefined)

// 个人自助注册已关闭（决策 D1）：新企业走官网 /register（企业注册），后台不再调用 /auth/register


/** 点邮件里的验证链接（决策 D21；无需登录） */
export const verifyEmail = (token: string): Promise<void> =>
  api.post('/auth/verify-email', { token }).then(() => undefined)

/** 重新发送验证邮件（60 秒一次） */
export const resendVerification = (): Promise<void> =>
  api.post('/auth/resend-verification').then(() => undefined)
