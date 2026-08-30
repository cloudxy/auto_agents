/**
 * new-api 中转站只读运维服务 - /newapi 端点封装（阶段三）
 *
 * 响应为后端 Pydantic 直出（无 ApiResponse 信封），与 services/llm.ts 解包方式一致。
 * 三端点全只读：overview（远程渠道+本地统计，可能降级 available=false）、
 * events / probe-results（本地表分页，始终可用）。
 */
import api from './api'

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

/** 分页列表（后端 Pydantic 直出） */
export interface PagedResponse<T> {
  total: number
  items: T[]
}

/** 分页查询参数 */
export interface PagedQuery {
  channel_id?: number
  page?: number
  page_size?: number
}

/** 中转站总览（渠道列表 + 本地统计；远程降级时仍 200） */
export const fetchNewapiOverview = (): Promise<NewapiOverview> => {
  return api.get('/newapi/overview') as unknown as Promise<NewapiOverview>
}

/** 渠道启停事件分页（时间倒序） */
export const fetchNewapiEvents = (params: PagedQuery): Promise<PagedResponse<ChannelEventItem>> => {
  return api.get('/newapi/events', { params }) as unknown as Promise<PagedResponse<ChannelEventItem>>
}

/** 探针结果分页（时间倒序） */
export const fetchNewapiProbeResults = (
  params: PagedQuery
): Promise<PagedResponse<ChannelProbeResultItem>> => {
  return api.get('/newapi/probe-results', {
    params,
  }) as unknown as Promise<PagedResponse<ChannelProbeResultItem>>
}
