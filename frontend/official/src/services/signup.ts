/**
 * 企业注册 service（SaaS S5，工单 71 归一）：公开租户开通端点
 */
import api, { unwrap } from './api'

export interface SignupResult {
  tenant: { name: string; slug: string }
  owner: { username: string }
}

export interface SignupPayload {
  company: string
  admin_email: string
  admin_password: string
  anonymous_id?: string
}

export const tenantSignup = (payload: SignupPayload): Promise<SignupResult> =>
  api.post('/public/tenant/signup', payload).then((r) => unwrap<SignupResult>(r))
