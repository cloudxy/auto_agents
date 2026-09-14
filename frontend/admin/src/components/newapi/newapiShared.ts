/**
 * new-api 运维域共享常量与格式化（工单 80 拆分自 NewApiOps.tsx）
 */
import { CHANNEL_STATUS, type DutyPageState, type ProbeVerdict } from '../../services/newapi'

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

/** verdict Tag：禁止「original 正品」中英叠词 */
export const VERDICT_TAG: Record<ProbeVerdict, { color: string; text: string }> = {
  original: { color: 'green', text: '正品' },
  spoofed: { color: 'red', text: '伪装' },
  offline: { color: 'default', text: '不可用' },
}

/** GWT-71.2 / 71.3 冻结句 */
export const DUTY_EMPTY_71_2 = '还没有平台模型，去网关登记'
export const DUTY_EMPTY_71_2_HINT =
  '平台 LLM 网关已连通，但还没有登记任何模型。登记后再刷新本页。'
export const DUTY_DEGRADE_71_3 = 'LLM 网关管理面不可达，仅本地事件/探针'
export const DUTY_DEGRADE_71_3_HINT =
  '现在读不到网关侧模型/部署。下方仍显示本库已有事件与探针。恢复后点刷新。'
export const DUTY_TABLE_UNAVAILABLE = '网关列表暂不可用'
export const DUTY_LOCAL_PROBE_EMPTY = '还没有本地探针记录。下次探针批次会显示在这里。'
export const DUTY_LOAD_FAILED = '值班页加载失败。检查网络后重试。'
export const DUTY_LIVE = '活'
export const DUTY_ROW_LIVE_STATUS = 'live'
export const FORBIDDEN_CHANNEL_EMPTY = '暂无渠道'

/** 屏 19：error/loading 后 hasLiveRow 压过 empty/degrade（含 duty_page_state）。 */
export type DutyBanner = 'loading' | 'error' | 'empty' | 'degrade' | 'live' | 'ok'

export const isDutyPageState = (value: unknown): value is DutyPageState =>
  value === 'empty' || value === 'degrade' || value === 'live'

export const isDutyLiveRow = (
  gatewayAvailable: boolean,
  registered: boolean,
  verdict: ProbeVerdict | null | undefined,
): boolean => Boolean(gatewayAvailable && registered && verdict === 'original')

/** 行「活」= 网关可达 ∧（API live ∨ 本地 original）；降级禁止标活。 */
export const showDutyLiveRow = (input: {
  dutyRowStatus?: string | null
  dutyRowStatusText?: string | null
  gatewayAvailable: boolean
  registered: boolean
  verdict?: ProbeVerdict | null
}): boolean => {
  if (!input.gatewayAvailable) return false
  if (input.dutyRowStatus != null || input.dutyRowStatusText != null) {
    return input.dutyRowStatus === DUTY_ROW_LIVE_STATUS || input.dutyRowStatusText === DUTY_LIVE
  }
  return isDutyLiveRow(input.gatewayAvailable, input.registered, input.verdict)
}

export const matchOverviewDuty = (
  models: Array<{
    gateway_ref: string
    model_name: string
    duty_row_status?: string | null
    duty_row_status_text?: string | null
  }> | undefined,
  gatewayRef: string | null,
  modelName: string,
): { dutyRowStatus: string | null; dutyRowStatusText: string | null } => {
  const list = models || []
  const hit = (gatewayRef && list.find((m) => m.gateway_ref === gatewayRef))
    || list.find((m) => m.model_name === modelName)
  return {
    dutyRowStatus: hit?.duty_row_status ?? null,
    dutyRowStatusText: hit?.duty_row_status_text ?? null,
  }
}

export const resolveDutyBanner = (input: {
  loading: boolean
  error: boolean
  available?: boolean
  modelTotal: number
  hasLiveRow: boolean
  dutyPageState?: string | null
}): DutyBanner => {
  if (input.loading) return 'loading'
  if (input.error) return 'error'
  if (input.hasLiveRow) return 'live'
  if (isDutyPageState(input.dutyPageState)) return input.dutyPageState
  if (input.available === false) return 'degrade'
  if (input.available && input.modelTotal === 0) return 'empty'
  return 'ok'
}

/** T-32 三问驾驶舱区级句（edge-states「中转站管控·总览」节，FR-84 同句式，不写第二套） */
export const CHANNELS_3Q_LOAD_FAILED = '渠道判定加载失败。检查网络后重试。'
export const EVENTS_3Q_LOAD_FAILED = '事件列表加载失败。检查网络后重试。'
export const EVENTS_24H_EMPTY = '最近 24 小时还没有事件。'
export const OFFLINE_LOCAL_HINT = '网络不可用，以下为已加载的本地数据。'
export const CELL_UNAVAILABLE = '暂不可用'
export const NO_BUDGET_WINDOW = '未配置预算窗口'
export const USED_QUOTA_SOURCE_HINT = '最近一次事件记录的窗口用量'

/** T-33 立即探测（GWT-98.4：行内进行中 + 完成行内更新） */
export const PROBING_TEXT = '探测中…'
export const PROBE_ACTION = '立即探测'
export const PROBE_TRIGGER_FAILED = '触发探测失败'
export const PROBE_DONE = '探测完成，判定与延迟已更新'

/** T-11（GWT-61.1）：探针 tab 最新批次伪装计数——数据源 overview.latest_batch_verdicts，
 *  文案入共享常量（冻结句纪律：不另起第二套说法） */
export const PROBE_LATEST_BATCH_LABEL = '最新批次'
export const PROBE_SPOOF_SUMMARY = (count: number): string => `伪装 ${count} 条`

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

/**
 * string gateway_ref → channel_id（数值引用直接取，镜像 backend
 * `newapi_api._channel_id_from_ref` 的数字分支）。非数值引用的 sha256 映射分支
 * 依赖 BigInt（构建 target=es5 不可用），**不在前端镜像**——返回 null，调用方以
 * 「—」降级，不编数据（缺口口径见 03-impl/T-32-evidence.md：建议后端在
 * channels/probe 响应直接携带 channel_id）。
 */
export const channelIdFromRef = (ref: string): number | null => {
  const text = (ref || '').trim()
  if (!/^\d+$/.test(text)) return null
  const value = Number(text)
  return value > 0 && Number.isSafeInteger(value) ? value : null
}
