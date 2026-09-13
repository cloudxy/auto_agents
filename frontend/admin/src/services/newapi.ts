/**
 * 值班页 /newapi 端点封装（T-18：网关模型列表；URL 一周期保留）
 */
import api, { unwrap } from './api'

export const CHANNEL_STATUS = {
  ENABLED: 1,
  MANUALLY_DISABLED: 2,
  AUTO_DISABLED: 3,
} as const

export type ProbeVerdict = 'original' | 'spoofed' | 'offline'
/** T-26 GET /newapi/overview 页级三态；缺省时 UI 回落本地派生 */
export type DutyPageState = 'empty' | 'degrade' | 'live'

export interface GatewayModel {
  gateway_ref: string
  model_name: string
  deployment_id?: string | null
  mode?: string | null
  api_base?: string | null
  api_key_masked?: string | null
  extra?: Record<string, unknown>
  duty_row_status?: string | null
  duty_row_status_text?: string | null
}

export interface NewapiOverview {
  available: boolean
  reason?: string | null
  empty_state?: string | null
  degrade_state?: string | null
  duty_page_state?: DutyPageState | null
  models: GatewayModel[]
  deployments: GatewayModel[]
  channels: unknown[]
  total: number
  events_24h: number
  latest_batch_id?: string | null
  latest_batch_verdicts: Partial<Record<ProbeVerdict, number>>
}

export interface ChannelEventItem {
  id: number
  channel_id: number
  action: string
  usage?: number | null
  limit_quota?: number | null
  window_hours?: number | null
  reason?: string | null
  source: string
  created_at?: string | null
}

export interface ChannelProbeResultItem {
  id: number
  channel_id: number
  model: string
  verdict: ProbeVerdict
  scores?: Record<string, unknown> | null
  latency_ms?: number | null
  batch_id: string
  created_at?: string | null
}

export interface PagedResponse<T> {
  total: number
  items: T[]
  page?: number
  page_size?: number
  total_pages?: number
}

export interface PagedQuery {
  channel_id?: number
  page?: number
  page_size?: number
}

export const fetchNewapiOverview = (): Promise<NewapiOverview> =>
  api.get('/newapi/overview').then((res) => unwrap<NewapiOverview>(res))

export const fetchNewapiEvents = (params: PagedQuery): Promise<PagedResponse<ChannelEventItem>> =>
  api
    .get('/newapi/events', { params })
    .then((res) => unwrap<PagedResponse<ChannelEventItem>>(res))

export const fetchNewapiProbeResults = (
  params: PagedQuery
): Promise<PagedResponse<ChannelProbeResultItem>> =>
  api
    .get('/newapi/probe-results', { params })
    .then((res) => unwrap<PagedResponse<ChannelProbeResultItem>>(res))

/** T-33 / GWT-98.4：立即探测回执（触发即返回 accepted + batch_id，不阻塞轮询循环） */
export interface ProbeTriggerResult {
  accepted: boolean
  gateway_ref: string
  batch_id: string
  reason?: string | null
}

export const triggerNewapiProbe = (gatewayRef: string): Promise<ProbeTriggerResult> =>
  api
    .post('/newapi/probe', { gateway_ref: gatewayRef })
    .then((res) => unwrap<ProbeTriggerResult>(res))

export interface ChannelConfigInfo {
  limit_quota: number
  window_hours: number
  cooldown_seconds: number
}

export interface GatewayModelWithConfig extends GatewayModel {
  config?: ChannelConfigInfo | null
  effective: ChannelConfigInfo
  effective_source: 'channel' | 'global' | 'none'
}

export const fetchChannelsWithConfig = (): Promise<GatewayModelWithConfig[]> =>
  api.get('/newapi/channels').then((res) => unwrap<GatewayModelWithConfig[]>(res))

export const setChannelConfig = (
  channelId: number,
  cfg: ChannelConfigInfo
): Promise<{ channel_id: number; config: ChannelConfigInfo }> =>
  api
    .put(`/newapi/channels/${channelId}/config`, cfg)
    .then((res) => unwrap<{ channel_id: number; config: ChannelConfigInfo }>(res))

export const setModelConfig = (
  gatewayRef: string,
  cfg: ChannelConfigInfo
): Promise<{ gateway_ref: string; config: ChannelConfigInfo }> =>
  api
    .put(`/newapi/models/${encodeURIComponent(gatewayRef)}/config`, cfg)
    .then((res) => unwrap<{ gateway_ref: string; config: ChannelConfigInfo }>(res))

export const clearChannelConfig = (
  channelId: number
): Promise<{ channel_id: number; cleared: boolean }> =>
  api
    .delete(`/newapi/channels/${channelId}/config`)
    .then((res) => unwrap<{ channel_id: number; cleared: boolean }>(res))

export const clearModelConfig = (
  gatewayRef: string
): Promise<{ gateway_ref: string; cleared: boolean }> =>
  api
    .delete(`/newapi/models/${encodeURIComponent(gatewayRef)}/config`)
    .then((res) => unwrap<{ gateway_ref: string; cleared: boolean }>(res))
