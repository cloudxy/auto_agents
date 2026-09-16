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
  /** T-05 列（FR-04）：治理目录精选星标。QA-4：list_catalog 之前不投影本
   * 字段，星标刷新即丢；QA-12：后端恒返回 int（0/1），不是 boolean。 */
  featured?: number
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

/** QA-8：后端默认只 upsert，不收回源里已消失的行（收回是破坏性动作，需要
 * 显式 retract=true）——这里保持不传，与后端安全默认对齐；治理台如果要暴露
 * "收回缺失行"，走单独的显式入口，不应该悄悄夹带在普通同步按钮里。 */
export const syncSource = (name: string): Promise<{ succeeded: number; failed: number }> =>
  api.post(`/capabilities/sources/${encodeURIComponent(name)}/sync`)
    .then((r) => unwrap<{ succeeded: number; failed: number }>(r))

/** T-02（FR-01）：同步 .agents——非破坏单通道，替代已退役的 scan-plugins。 */
export interface AgentsHubSyncResult {
  inserted: number
  updated: number
  unchanged: number
  failed: number
  total: number
  failed_items?: Array<{ asset_type: string; name: string; reason?: string }>
}

export const syncAgentsHub = (): Promise<AgentsHubSyncResult> =>
  api.post('/capabilities/sync-agents-hub')
    .then((r) => unwrap<AgentsHubSyncResult>(r))

/** T-15（FR-02）：失源行清理。dry_run=true 只取同构预览不落库。 */
export interface PruneMissingResult {
  pruned: Array<{ asset_type: string; name: string }>
  live_total: number
  disk_total: number
}

export const pruneMissingAssets = (dryRun = false): Promise<PruneMissingResult> =>
  api.post('/capabilities/assets/prune-missing', undefined, {
    params: dryRun ? { dry_run: 'true' } : undefined,
  }).then((r) => unwrap<PruneMissingResult>(r))

/** T-12（FR-07）：目录导入两段式。filename = webkitRelativePath（服务端按树判型）。 */
export interface TreeImportAsset {
  asset_type: string
  name: string
  action: 'create' | 'update'
  origin_path?: string | null
  bundled?: TreeImportAsset[]
}

export interface TreeImportSkip { path: string; reason: string }

export interface TreePreviewResult {
  assets: TreeImportAsset[]
  skipped: TreeImportSkip[]
  counts: { skill: number; plugin: number; command: number; agent: number }
  files_total: number
}

export interface TreeConfirmResult {
  created: number
  updated: number
  failed: Array<{ name: string; reason: string }>
  skipped: TreeImportSkip[]
  batch_id?: string | number | null
}

const appendTreeFiles = (form: FormData, files: File[]): void => {
  for (const file of files) {
    const rel = (file as File & { webkitRelativePath?: string }).webkitRelativePath
    form.append('files', file, rel || file.name)
  }
}

export const previewTreeImport = (
  files: File[],
  onUploadProgress?: (event: AxiosProgressEvent) => void,
): Promise<TreePreviewResult> => {
  const form = new FormData()
  appendTreeFiles(form, files)
  return api.post('/capabilities/import/tree/preview', form, { onUploadProgress })
    .then((r) => unwrap<TreePreviewResult>(r))
}

export const confirmTreeImport = (
  files: File[],
  onUploadProgress?: (event: AxiosProgressEvent) => void,
): Promise<TreeConfirmResult> => {
  const form = new FormData()
  appendTreeFiles(form, files)
  return api.post('/capabilities/import/tree/confirm', form, { onUploadProgress })
    .then((r) => unwrap<TreeConfirmResult>(r))
}

/** T-11（FR-04/附加 d）：精选开关 + 示例维护（治理门面 PATCH）。 */
export const patchFeatured = (
  assetType: string,
  name: string,
  featured: boolean,
): Promise<AssetRow> =>
  api.patch(
    `/capabilities/${encodeURIComponent(assetType)}/${encodeURIComponent(name)}/featured`,
    { featured },
  ).then((r) => unwrap<AssetRow>(r))

export const patchExamples = (
  assetType: string,
  name: string,
  examples: string[],
): Promise<AssetRow> =>
  api.patch(
    `/capabilities/${encodeURIComponent(assetType)}/${encodeURIComponent(name)}/examples`,
    { examples },
  ).then((r) => unwrap<AssetRow>(r))

export const verifyPlugin = (name: string): Promise<PluginVerifyResult> =>
  api.post(`/capabilities/plugins/${encodeURIComponent(name)}/verify`)
    .then((r) => unwrap<PluginVerifyResult>(r))

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
  title?: string | null
  description?: string | null
  category?: string
  listing_state?: string
  subscribable?: boolean
  hosts?: string[]
  market_closed?: boolean
  message?: string | null
  /** T-04/T-10 详情增量（contract API #8）：md 正文三源 / 示例 / 闸值 / 预览态 */
  skill_md?: string | null
  body_md?: string | null
  persona_md?: string | null
  examples?: string[] | null
  gate_open?: boolean
  preview?: boolean
  install_count?: number | null
  origin_plugin_name?: string | null
  featured?: number
  logo?: string | null
  background?: string | null
  updated_at?: string | null
}

export type PublicListQuery = {
  type?: string
  q?: string
  host?: string
  category?: string
  page?: number
  page_size?: number
  /** T-08（FR-04）：smart | latest | hot */
  sort?: string
  /** QA-2 修复：请求侧 preview 参数（AD-5c 超管预览旁路）——响应里的
   * `PublicShelfList.preview` 只是回显，真正驱动闸/listed 豁免的是这个请求参数。
   * 后端只认平台管理员的会话，非管理员传了也被忽略。 */
  preview?: boolean
}

export type PublicShelfItem = {
  asset_type: string
  name: string
  title?: string | null
  description?: string | null
  category?: string
  listing_state?: string | null
  subscribable?: boolean
  hosts?: string[]
  slash?: string | null
  score?: number | null
  tier?: string | null
  logo?: string | null
  background?: string | null
  origin_plugin_name?: string | null
  featured?: number
  updated_at?: string | null
}

export type PublicShelfList = {
  items: PublicShelfItem[]
  total?: number
  page?: number
  page_size?: number
  has_more?: boolean
  market_closed?: boolean
  empty?: boolean
  message?: string
  /** T-06/T-08：hot 无全库计数时服务端回 smart（UI 静默接受，GWT-04.4） */
  sort_applied?: string
  /** T-13：管理员预览旁路（AD-5c） */
  preview?: boolean
  gate_open?: boolean
  live_total?: number
}

const compactPublicQuery = (params: PublicListQuery): Record<string, string | number> => {
  const page = params.page ?? 1
  const query: Record<string, string | number> = { page_size: params.page_size ?? 20, page }
  if (params.type) query.type = params.type
  if (params.q) query.q = params.q
  if (params.host) query.host = params.host
  if (params.category) query.category = params.category
  if (params.sort) query.sort = params.sort
  if (params.preview) query.preview = 'true'
  return query
}

export const listPublicAssets = (
  params: PublicListQuery = {},
): Promise<PublicShelfList> =>
  api.get('/public/capabilities', { params: compactPublicQuery(params) })
    .then((r) => unwrap<PublicShelfList>(r))

export const getPowerMarket = (): Promise<{ enabled: boolean }> =>
  api.get('/admin/power-market').then((r) => unwrap<{ enabled: boolean }>(r))

export const putPowerMarket = (enabled: boolean): Promise<{ enabled: boolean }> =>
  api.put('/admin/power-market', { enabled }).then((r) => unwrap<{ enabled: boolean }>(r))

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
  preview?: boolean,
): Promise<PublicCapabilityCard> =>
  api.get(`/public/capabilities/${encodeURIComponent(assetType)}/${encodeURIComponent(name)}`, {
    params: preview ? { preview: 'true' } : undefined,
  }).then((r) => unwrap<PublicCapabilityCard>(r))
