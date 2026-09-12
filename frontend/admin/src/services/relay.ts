/**
 * 渠道组令牌（FR-60）。产品名「渠道组令牌」，不与出站拉数钥匙混名（X-KEY）。
 * T-10：读模型一次拉组+令牌，并透传信封 message——空态句（GWT-60.4）与
 * 找管理员句（GWT-60.7）单一来源在 relay_service，页面直接渲染不另造第二套。
 */
import api, { unwrap, type ApiEnvelope } from './api'

export interface RelayGroupRow {
  id: number
  name: string
  rpm_limit: number
  tpm_limit: number
  models: string[]
  status: string
}

export interface RelayTokenRow {
  id: number
  group_id: number
  name: string
  key_prefix: string
  quota_tokens: number
  /** 本地缓存用量列（QA-08：列表不打网关）；null=暂不可知，不得画成 0 */
  used_tokens: number | null
  status: string
  plaintext_key?: string | null
}

/** 渠道组页读模型：data + 信封 message（空态/角色旁注句） */
export interface RelayPageData {
  groups: RelayGroupRow[]
  tokens: RelayTokenRow[]
  groupsMessage: string
  tokensMessage: string
}

const envelopeMessage = (r: unknown): string => (r as ApiEnvelope<unknown>)?.message || ''

export const fetchRelayPage = async (): Promise<RelayPageData> => {
  const [g, t] = await Promise.all([api.get('/relay/groups'), api.get('/relay/tokens')])
  return {
    groups: unwrap<RelayGroupRow[]>(g),
    tokens: unwrap<RelayTokenRow[]>(t),
    groupsMessage: envelopeMessage(g),
    tokensMessage: envelopeMessage(t),
  }
}

export const createRelayGroup = (body: {
  name: string
  rpm_limit?: number
  tpm_limit?: number
  models?: string[]
}): Promise<RelayGroupRow> =>
  api.post('/relay/groups', body).then((r) => unwrap<RelayGroupRow>(r))

export const patchRelayGroup = (
  id: number, body: { status?: string; rpm_limit?: number; tpm_limit?: number; models?: string[] },
): Promise<RelayGroupRow> =>
  api.patch(`/relay/groups/${id}`, body).then((r) => unwrap<RelayGroupRow>(r))

export const issueRelayToken = (body: {
  group_id: number
  name: string
  quota_tokens?: number
}): Promise<RelayTokenRow> =>
  api.post('/relay/tokens', body).then((r) => unwrap<RelayTokenRow>(r))

export const revokeRelayToken = (id: number): Promise<RelayTokenRow> =>
  api.delete(`/relay/tokens/${id}`).then((r) => unwrap<RelayTokenRow>(r))
