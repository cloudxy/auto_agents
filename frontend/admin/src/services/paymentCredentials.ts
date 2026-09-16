/**
 * 支付渠道商户凭据（超管专属）：支付宝/微信支付真实网关接入。
 * 密钥只写不回读——GET 只见掩码 `secrets_masked`；PUT 每次都要求重新粘贴
 * 完整密钥包（不支持"只改商户号不改密钥"式增量更新，避免误判部分字段）。
 */
import api, { unwrap } from './api'

export type PaymentChannel = 'alipay' | 'wechat'

export interface PaymentChannelCredentialView {
  channel: PaymentChannel
  configured: boolean
  merchant_no?: string | null
  secrets_masked?: string | null
  key_version?: number | null
  rotated_at?: string | null
  created_by?: string | null
  updated_by?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface PaymentChannelCredentialListOut {
  channels: PaymentChannelCredentialView[]
}

export interface AlipaySecretsForm {
  app_id: string
  app_private_key: string
  alipay_public_key: string
}

export interface WechatSecretsForm {
  mch_id: string
  api_v3_key: string
  apiclient_key: string
  cert_serial_no: string
  appid: string
}

export const fetchPaymentCredentials = (): Promise<PaymentChannelCredentialListOut> =>
  api.get('/admin/payment-credentials').then((r) => unwrap<PaymentChannelCredentialListOut>(r))

export const putPaymentCredential = (body: {
  channel: PaymentChannel
  merchant_no: string
  secrets: string
}): Promise<PaymentChannelCredentialView> =>
  api.put('/admin/payment-credentials', body).then((r) => unwrap<PaymentChannelCredentialView>(r))

export const deletePaymentCredential = (channel: PaymentChannel): Promise<{ channel: string; configured: boolean }> =>
  api.delete(`/admin/payment-credentials/${channel}`)
    .then((r) => unwrap<{ channel: string; configured: boolean }>(r))

export interface ValidatePaymentCredentialResult {
  channel: PaymentChannel
  valid: boolean
  checked: string
}

export const validatePaymentCredential = (channel: PaymentChannel): Promise<ValidatePaymentCredentialResult> =>
  api.post(`/admin/payment-credentials/${channel}/validate`)
    .then((r) => unwrap<ValidatePaymentCredentialResult>(r))

/** 结构化表单 → 后端密钥包 JSON 字符串（不做字段名改写，直接照抄官方术语）。 */
export const buildAlipaySecretsPayload = (form: AlipaySecretsForm): string => JSON.stringify(form)
export const buildWechatSecretsPayload = (form: WechatSecretsForm): string => JSON.stringify(form)
