/**
 * new-api 中转站只读运维服务 - /newapi 端点封装（阶段三）
 *
 * 响应为后端统一信封（ADR-001）：overview 为 ApiResponse，
 * events / probe-results 为 PaginatedResponse（data.items/total），
 * service 层统一解包 data，页面组件拿到的仍是裸结构。
 */
import api, { unwrap } from './api'

/** 渠道状态常量（与 new-api model/channel.go 语义对齐） */
export const CHANNEL_STATUS = {
  ENABLED: 1,
  MANUALLY_DISABLED: 2,
  AUTO_DISABLED: 3,
} as const

/** new-api 渠道快照（宽松映射：已知字段 + extra 未知字段透传） */
export interface NewapiChannel {
  id: number
  name: string
  status: number
  type: number
  used_quota?: number | null
  balance?: number | null
  /** 测速延迟毫秒（-1 表示未测） */
  response_time?: number | null
  /** 上次测速 unix 秒 */
  test_time?: number | null
  models?: string | null
  group?: string | null
  base_url?: string | null
  priority?: number | null
  weight?: number | null
  created_time?: number | null
  extra?: Record<string, unknown>
}

/** 探针判定（与后端 ProbeVerdict 枚举对齐） */
export type ProbeVerdict = 'original' | 'spoofed' | 'offline'

/** 中转站总览（远程渠道 + 本地统计；远程不可达时 available=false 降级） */
export interface NewapiOverview {
  available: boolean
  reason?: string | null
  channels: NewapiChannel[]
  total: number
  /** 近 24h 渠道事件数（本地表） */
  events_24h: number
  /** 最近一次探针批次（无记录时 null） */
  latest_batch_id?: string | null
  /** 最近批次 verdict 分布计数 */
  latest_batch_verdicts: Partial<Record<ProbeVerdict, number>>
}

/** 渠道启停事件 */
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

/** 探针结果 */
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

/** 分页列表（信封 data 载荷；page/page_size/total_pages 为分页信封附赠字段） */
export interface PagedResponse<T> {
  total: number
  items: T[]
  page?: number
  page_size?: number
  total_pages?: number
}

/** 分页查询参数 */
export interface PagedQuery {
  channel_id?: number
  page?: number
  page_size?: number
}

/** 中转站总览（渠道列表 + 本地统计；远程降级时仍 200） */
export const fetchNewapiOverview = (): Promise<NewapiOverview> =>
  api.get('/newapi/overview').then((res) => unwrap<NewapiOverview>(res))

/** 渠道启停事件分页（时间倒序） */
export const fetchNewapiEvents = (params: PagedQuery): Promise<PagedResponse<ChannelEventItem>> =>
  api
    .get('/newapi/events', { params })
    .then((res) => unwrap<PagedResponse<ChannelEventItem>>(res))

/** 探针结果分页（时间倒序） */
export const fetchNewapiProbeResults = (
  params: PagedQuery
): Promise<PagedResponse<ChannelProbeResultItem>> =>
  api
    .get('/newapi/probe-results', { params })
    .then((res) => unwrap<PagedResponse<ChannelProbeResultItem>>(res))

// ---------------- 渠道额度调度配置（4.2 接线：写路径） ----------------

/** 渠道级额度配置（与 Redis hash newapi:channel:cfg:{id} 字段对应） */
export interface ChannelConfigInfo {
  limit_quota: number
  window_hours: number
  cooldown_seconds: number
}

/** 渠道快照 + 调度配置合并视图（GET /newapi/channels） */
export interface ChannelWithConfig extends NewapiChannel {
  config?: ChannelConfigInfo | null
  effective: ChannelConfigInfo
  effective_source: 'channel' | 'global' | 'none'
}

/** 渠道列表 + 配置合并视图（远程不可达时后端返回业务码 502，错误提示走拦截器） */
export const fetchChannelsWithConfig = (): Promise<ChannelWithConfig[]> =>
  api.get('/newapi/channels').then((res) => unwrap<ChannelWithConfig[]>(res))

/** 写入渠道级额度配置（limit_quota=0 = 显式关闭该渠道调度） */
export const setChannelConfig = (
  channelId: number,
  cfg: ChannelConfigInfo
): Promise<{ channel_id: number; config: ChannelConfigInfo }> =>
  api
    .put(`/newapi/channels/${channelId}/config`, cfg)
    .then((res) => unwrap<{ channel_id: number; config: ChannelConfigInfo }>(res))

/** 清除渠道级配置（回退全局默认；无全局默认则退出纳管） */
export const clearChannelConfig = (channelId: number): Promise<{ channel_id: number; cleared: boolean }> =>
  api
    .delete(`/newapi/channels/${channelId}/config`)
    .then((res) => unwrap<{ channel_id: number; cleared: boolean }>(res))
