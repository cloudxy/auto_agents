/**
 * 能力资产域 service（P6 Hub，工单 71 归一）：四类资产目录 + 插件/专家/专家团操作
 */
import type { AxiosProgressEvent } from 'axios'

import api, { unwrap } from './api'

export interface AssetRow {
  id: number
  asset_type: string
  name: string
  title: string
  category: string
  status: string
  tier?: string | null
  score?: number | null
  sync_state: string
  listing_state?: string
  listed_at?: string | null
  source_type?: string
}

export interface PluginVerifyResult {
  health: string
  detail: Record<string, { health: string; detail: string }>
}

export interface PluginDetail {
  name: string
  health_status?: string
  listing_state?: string
  listed_at?: string | null
  mcp_servers?: Record<string, unknown>
  bundled_skills?: string[]
}

export const listAssets = (
  type?: string, listingState?: string,
): Promise<{ total: number; items: AssetRow[] }> =>
  api.get('/capabilities', { params: { type, listing_state: listingState, page_size: 50 } })
    .then((r) => unwrap<{ total: number; items: AssetRow[] }>(r))

export const patchListing = (
  assetType: string,
  name: string,
  listing_state: string,
  confirm = false,
): Promise<AssetRow> =>
  api.patch(
    `/capabilities/${encodeURIComponent(assetType)}/${encodeURIComponent(name)}/listing`,
    { listing_state, confirm },
  ).then((r) => unwrap<AssetRow>(r))

export const getPlugin = (name: string): Promise<PluginDetail> =>
  api.get(`/capabilities/plugins/${encodeURIComponent(name)}`)
    .then((r) => unwrap<PluginDetail>(r))

export interface ImportItemResult {
  asset_type: string
  name: string
  status: 'succeeded' | 'failed' | 'skipped'
  reason?: string | null
  asset_id?: number | null
}

export interface ImportResult {
  batch_id: number
  origin: string
  status: string
  total: number
  succeeded: number
  failed: number
  skipped: number
  items: ImportItemResult[]
  message?: string | null
}

/** T-36 一键导入（FR-100 / ADR-0023）：multipart file（可重复）或 directory 二选一。
 * 逐条失败原因已是后端成品中文句，调用方直接渲染。 */
export const importAssets = (
  payload: { files?: File[]; directory?: string },
  onUploadProgress?: (event: AxiosProgressEvent) => void,
): Promise<ImportResult> => {
  const form = new FormData()
  for (const file of payload.files || []) form.append('file', file)
  if (payload.directory) form.append('directory', payload.directory)
  return api.post('/capabilities/import', form, { onUploadProgress })
    .then((r) => unwrap<ImportResult>(r))
}

export interface SourceRow {
  id: number
  name: string
  source_kind: string
  uri: string
  is_enabled: number
  last_sync_at?: string | null
  last_succeeded: number
  last_failed: number
  last_error?: string | null
}

export const listSources = (): Promise<{ total: number; items: SourceRow[] }> =>
  api.get('/capabilities/sources').then((r) => unwrap<{ total: number; items: SourceRow[] }>(r))

export const registerSource = (body: {
  name: string
  source_kind: string
  uri: string
}): Promise<SourceRow> =>
  api.post('/capabilities/sources', body).then((r) => unwrap<SourceRow>(r))

export const syncSource = (name: string): Promise<{ succeeded: number; failed: number }> =>
  api.post(`/capabilities/sources/${encodeURIComponent(name)}/sync`)
    .then((r) => unwrap<{ succeeded: number; failed: number }>(r))

export const scanPlugins = (): Promise<void> =>
  api.post('/capabilities/scan-plugins').then(() => undefined)

export const verifyPlugin = (name: string): Promise<PluginVerifyResult> =>
  api.post(`/capabilities/plugins/${encodeURIComponent(name)}/verify`)
    .then((r) => unwrap<PluginVerifyResult>(r))

export const scanExperts = (): Promise<void> =>
  api.post('/capabilities/scan-experts').then(() => undefined)

export const createTeam = (payload: Record<string, unknown>): Promise<void> =>
  api.post('/capabilities/teams', payload).then(() => undefined)

/** T-37（FR-101）：团队成员引用——成员域扩 expert∪agent；旧数据为名称字符串（按专家） */
export interface TeamMemberRef {
  type: 'expert' | 'agent'
  name: string
}

export interface TeamDetail {
  name: string
  title: string
  status: string
  leader: string
  members: (TeamMemberRef | string)[]
  workflow_md: string
}

export const getTeamDetail = (name: string): Promise<TeamDetail> =>
  api.get(`/capabilities/teams/${encodeURIComponent(name)}`)
    .then((r) => unwrap<TeamDetail>(r))

export interface SubscribeResult {
  created: boolean
  already_subscribed?: boolean
  message: string
  host: string
  asset_id: number
}

export interface PublicCapabilityCard {
  name: string
  asset_type: string
  listing_state?: string
  subscribable?: boolean
  hosts?: string[]
}

export interface InstallRow {
  id: number
  asset_id: number
  asset_name: string
  asset_type: string
  host: string
  enabled: number
  trusted: number
  delisted?: boolean
  delisted_label?: string | null
  flags_locked?: boolean
  can_change_flags?: boolean
  can_uninstall?: boolean
  resubscribe_allowed?: boolean
  resubscribe_hint?: string | null
}

export const subscribeCapability = (
  assetType: string,
  name: string,
  host: string,
): Promise<SubscribeResult> =>
  api.post(`/capabilities/${encodeURIComponent(assetType)}/${encodeURIComponent(name)}/subscribe`, { host })
    .then((r) => unwrap<SubscribeResult>(r))

export const listInstalls = (): Promise<{ total: number; items: InstallRow[] }> =>
  api.get('/capabilities/installs').then((r) => unwrap<{ total: number; items: InstallRow[] }>(r))

export const patchInstall = (
  id: number,
  body: { enabled?: number; trusted?: number },
): Promise<InstallRow> =>
  api.patch(`/capabilities/installs/${id}`, body).then((r) => unwrap<InstallRow>(r))

export const uninstallInstall = (id: number): Promise<{ id: number; deleted: boolean }> =>
  api.delete(`/capabilities/installs/${id}`).then((r) => unwrap<{ id: number; deleted: boolean }>(r))

export const fetchPublicCapability = (
  assetType: string,
  name: string,
): Promise<PublicCapabilityCard> =>
  api.get(`/public/capabilities/${encodeURIComponent(assetType)}/${encodeURIComponent(name)}`)
    .then((r) => unwrap<PublicCapabilityCard>(r))
