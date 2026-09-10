import api, { unwrap } from './api'

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
  used_tokens: number
  status: string
  plaintext_key?: string | null
}

export const listRelayGroups = (): Promise<RelayGroupRow[]> =>
  api.get('/relay/groups').then((r) => unwrap<RelayGroupRow[]>(r))

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

export const listRelayTokens = (): Promise<RelayTokenRow[]> =>
  api.get('/relay/tokens').then((r) => unwrap<RelayTokenRow[]>(r))

export const issueRelayToken = (body: {
  group_id: number
  name: string
  quota_tokens?: number
}): Promise<RelayTokenRow> =>
  api.post('/relay/tokens', body).then((r) => unwrap<RelayTokenRow>(r))

export const revokeRelayToken = (id: number): Promise<RelayTokenRow> =>
  api.delete(`/relay/tokens/${id}`).then((r) => unwrap<RelayTokenRow>(r))
