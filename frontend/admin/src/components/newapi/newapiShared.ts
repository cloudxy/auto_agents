/**
 * new-api 运维域共享常量与格式化（工单 80 拆分自 NewApiOps.tsx）
 */
import { CHANNEL_STATUS, type ProbeVerdict } from '../../services/newapi'

export const STATUS_TAG: Record<number, { color: string; text: string }> = {
  [CHANNEL_STATUS.ENABLED]: { color: 'green', text: '启用' },
  [CHANNEL_STATUS.MANUALLY_DISABLED]: { color: 'orange', text: '人工禁用' },
  [CHANNEL_STATUS.AUTO_DISABLED]: { color: 'red', text: '自动禁用' },
}

/** 常见渠道类型名（new-api 常量，未收录的展示 type 数字） */
export const CHANNEL_TYPE_NAMES: Record<number, string> = {
  1: 'OpenAI',
  14: 'Anthropic',
  24: 'Gemini',
}

/** verdict Tag 映射（original 绿 / spoofed 红 / offline 灰） */
export const VERDICT_TAG: Record<ProbeVerdict, { color: string; text: string }> = {
  original: { color: 'green', text: 'original 正品' },
  spoofed: { color: 'red', text: 'spoofed 伪装' },
  offline: { color: 'default', text: 'offline 不可用' },
}

/** 动作 Tag 映射 */
export const ACTION_TAG: Record<string, { color: string; text: string }> = {
  disabled: { color: 'red', text: '下线' },
  enabled: { color: 'green', text: '上线' },
}

export const fmtTime = (v?: string | null): string => {
  if (!v) return '-'
  const d = new Date(v)
  return Number.isNaN(d.getTime()) ? v : d.toLocaleString('zh-CN', { hour12: false })
}

export const fmtQuota = (v?: number | null): string =>
  v === null || v === undefined ? '-' : Number(v).toLocaleString('zh-CN')

export const fmtMoney = (v?: number | null): string =>
  v === null || v === undefined ? '-' : `$${Number(v).toFixed(2)}`

export const fmtLatency = (v?: number | null): string =>
  v === null || v === undefined || v < 0 ? '-' : `${v} ms`

export const DEFAULT_PAGE_SIZE = 10

/** 渠道 ID 过滤输入解析（非正整数视为清空过滤） */
export const parseChannelId = (raw: string): number | undefined => {
  const n = Number(raw.trim())
  return raw.trim() && Number.isInteger(n) && n > 0 ? n : undefined
}
