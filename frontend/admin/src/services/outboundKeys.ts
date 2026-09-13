/**
 * 出站拉数钥匙（FR-51 / ADR-0020）。产品名「出站拉数钥匙」，与渠道组令牌（sk-）分平面（X-KEY）。
 * 空态句走信封 message 单一来源（T-04：data=[] 时 message=spec 冻结句），页面直接渲染不另造第二套。
 * 明文只在签发响应（plaintext_key）出现一次；列表只回前缀与派生状态（GWT-51.8）。
 */
import api, { unwrap, type ApiEnvelope } from './api'

export interface OutboundKeyRow {
  id: number
  name: string | null
  key_prefix: string
  /** active=已签发；revoked=已吊销（revoked_at 派生） */
  status: string
  revoked_at: string | null
  created_at: string
}

export interface OutboundKeyIssuedRow extends OutboundKeyRow {
  /** 明文钥匙；仅签发响应返回一次，库内只存 hash（GWT-51.1） */
  plaintext_key: string
}

/** 列表读模型：data + 信封 message（空态句单一来源在 outbound_key 域） */
export interface OutboundKeysData {
  keys: OutboundKeyRow[]
  message: string
}

const envelopeMessage = (r: unknown): string => (r as ApiEnvelope<unknown>)?.message || ''

export const fetchOutboundKeys = async (): Promise<OutboundKeysData> => {
  const r = await api.get('/outbound/keys')
  return { keys: unwrap<OutboundKeyRow[]>(r), message: envelopeMessage(r) }
}

export const issueOutboundKey = (body: { name?: string }): Promise<OutboundKeyIssuedRow> =>
  api.post('/outbound/keys', body).then((r) => unwrap<OutboundKeyIssuedRow>(r))

export const revokeOutboundKey = (id: number): Promise<OutboundKeyRow> =>
  api.delete(`/outbound/keys/${id}`).then((r) => unwrap<OutboundKeyRow>(r))
