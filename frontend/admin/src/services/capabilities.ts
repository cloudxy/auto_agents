/**
 * 能力资产域 service（P6 Hub，工单 71 归一）：四类资产目录 + 插件/专家/专家团操作
 */
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
}

export interface PluginVerifyResult {
  health: string
  detail: Record<string, { health: string; detail: string }>
}

export const listAssets = (type?: string): Promise<{ total: number; items: AssetRow[] }> =>
  api.get('/capabilities', { params: { type, page_size: 50 } })
    .then((r) => unwrap<{ total: number; items: AssetRow[] }>(r))

export const scanPlugins = (): Promise<void> =>
  api.post('/capabilities/scan-plugins').then(() => undefined)

export const verifyPlugin = (name: string): Promise<PluginVerifyResult> =>
  api.post(`/capabilities/plugins/${encodeURIComponent(name)}/verify`)
    .then((r) => unwrap<PluginVerifyResult>(r))

export const scanExperts = (): Promise<void> =>
  api.post('/capabilities/scan-experts').then(() => undefined)

export const createTeam = (payload: Record<string, unknown>): Promise<void> =>
  api.post('/capabilities/teams', payload).then(() => undefined)
