/** T-10 / 屏 15：与官网屏 3 同一对关闭句/空货架句。禁定价可买四字。 */

export const MARKET_CLOSED = '能力市场未开放'
export const MARKET_CLOSED_HINT = '开放后，已上架的能力会出现在这里。'
export const EMPTY_SHELF = '暂无已上架能力'
export const EMPTY_SHELF_HINT = '已上架且过许可的能力会出现在这里。'
/** T-08 整架空新句（edge-states §4.2：预览态给 live_total 治理线索） */
export const emptyShelfHint = (liveTotal?: number | null): string => (
  liveTotal != null && liveTotal > 0
    ? `上架后能力会出现在这里。当前有 ${liveTotal} 个资产未上架。`
    : '上架后能力会出现在这里。'
)
export const FILTER_EMPTY = '没有符合条件的能力'
export const LOAD_FAIL = '市场列表加载失败'
export const LOAD_FAIL_HINT = '检查网络后重试'
export const READONLY_SUBSCRIBE = '当前账号不能订阅，请联系企业管理员'
export const ENABLE_HOST = '启用到宿主'

/** T-08（FR-03/04，edge-states §10 新增成品句） */
export const TAB_EMPTY = '暂无该类资产'
export const tabEmptyHint = (typeText: string): string =>
  `同步 .agents 后，${typeText} 会出现在这里。`
export const SYNC_NOW = '立即同步'
export const GO_GOVERNANCE = '去治理目录'
export const NO_DESC = '暂无描述'
export const PREVIEW_BADGE = '预览模式 · 市场未对租户开放，你看到的是上架后的展示效果'
export const SORT_OPTIONS = [
  { value: 'smart', label: '综合' },
  { value: 'hot', label: '最热' },
  { value: 'latest', label: '最新' },
] as const
export type SortKey = (typeof SORT_OPTIONS)[number]['value']
export const resolveSort = (raw: string | null): SortKey => {
  const hit = SORT_OPTIONS.find((o) => o.value === raw)
  return hit ? hit.value : 'smart'
}

export const PUBLIC_TYPES = [
  { key: 'skill', label: '技能' },
  { key: 'plugin', label: '插件' },
  { key: 'command', label: '命令' },
  { key: 'agent', label: '智能体' },
  { key: 'team', label: '专家团' },
] as const

export const PUBLIC_KEYS = new Set<string>(PUBLIC_TYPES.map((t) => t.key))

/** T-08：类型中文（卡片副标题兜底 / tab 空态说明 / 标签） */
export const typeLabelOf = (key: string): string =>
  PUBLIC_TYPES.find((t) => t.key === key)?.label || key

export const LEGACY_MAP: Record<string, string> = {
  expert: 'agent',
  expert_team: 'team',
}

export const HOST_OPTIONS = [
  { value: 'grok', label: 'Grok' },
  { value: 'zcode', label: 'ZCode' },
  { value: 'kimi', label: 'Kimi' },
  { value: 'claude', label: 'Claude' },
] as const

export const cardTitle = (asset: { title?: string | null; name: string }): string => {
  const title = (asset.title || '').trim()
  if (title && !title.includes('__')) return title
  const raw = title || asset.name
  const at = raw.lastIndexOf('__')
  if (at >= 0) {
    const short = raw.slice(at + 2).trim()
    if (short) return short
  }
  return raw
}

export type ShelfFilterValues = {
  type: string
  q: string
  host: string
  category: string
}

export const hasActiveFilters = (opts: ShelfFilterValues): boolean => {
  if (opts.type && opts.type !== 'all') return true
  return Boolean(opts.q || opts.host || opts.category)
}

const FILTER_ECHO_LABELS: Record<'type' | 'q' | 'host' | 'category', string> = {
  type: '类型',
  q: '关键词',
  host: '宿主',
  category: '分类',
}

export const activeFilterEcho = (
  opts: ShelfFilterValues,
): Array<{ key: keyof typeof FILTER_ECHO_LABELS; label: string; value: string }> => {
  const rows: Array<{ key: keyof typeof FILTER_ECHO_LABELS; label: string; value: string }> = []
  if (opts.type && opts.type !== 'all') {
    rows.push({ key: 'type', label: FILTER_ECHO_LABELS.type, value: opts.type })
  }
  if (opts.q) rows.push({ key: 'q', label: FILTER_ECHO_LABELS.q, value: opts.q })
  if (opts.host) rows.push({ key: 'host', label: FILTER_ECHO_LABELS.host, value: opts.host })
  if (opts.category) {
    rows.push({ key: 'category', label: FILTER_ECHO_LABELS.category, value: opts.category })
  }
  return rows
}

export type ResolvedType = { key: string; illegal: boolean }

export const resolveType = (raw: string | null): ResolvedType => {
  const value = raw ?? ''
  if (!value) return { key: 'all', illegal: false }
  if (PUBLIC_KEYS.has(value)) return { key: value, illegal: false }
  if (LEGACY_MAP[value]) return { key: LEGACY_MAP[value], illegal: false }
  return { key: value, illegal: true }
}
