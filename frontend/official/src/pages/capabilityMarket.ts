/** 官网能力市场列表：类型/宿主筛、卡片主标题（ADR-0012）。 */

export const PUBLIC_TYPES = [
  { key: 'skill', label: '技能' },
  { key: 'plugin', label: '插件' },
  { key: 'command', label: '命令' },
  { key: 'agent', label: '智能体' },
  { key: 'team', label: '专家团' },
] as const

export const PUBLIC_KEYS = new Set<string>(PUBLIC_TYPES.map((t) => t.key))

export const LEGACY_MAP: Record<string, string> = {
  expert: 'agent',
  expert_team: 'team',
}

export const TYPE_LABELS: Record<string, string> = Object.fromEntries(
  PUBLIC_TYPES.map((t) => [t.key, t.label]),
)

export const HOST_OPTIONS = [
  { value: 'grok', label: 'Grok' },
  { value: 'zcode', label: 'ZCode' },
  { value: 'kimi', label: 'Kimi' },
  { value: 'claude', label: 'Claude' },
] as const

/** T-10 / 屏 3：关闭句 vs 空货架句。两句不得混用。禁定价可买四字。 */
export const MARKET_CLOSED = '能力市场未开放'
export const MARKET_CLOSED_HINT = '开放后，已上架的能力会出现在这里。'
export const EMPTY_SHELF = '暂无已上架能力'
export const EMPTY_SHELF_HINT = '已上架且过许可的能力会出现在这里。'
export const FILTER_EMPTY = '没有符合条件的能力'
export const LOAD_FAIL = '市场列表加载失败'
export const LOAD_FAIL_HINT = '检查网络后重试'

export type ResolvedType = { key: string; illegal: boolean }

export const resolveType = (raw: string | null, pathIsSkills: boolean): ResolvedType => {
  const value = raw ?? (pathIsSkills ? 'skill' : '')
  if (!value) return { key: 'all', illegal: false }
  if (PUBLIC_KEYS.has(value)) return { key: value, illegal: false }
  if (LEGACY_MAP[value]) return { key: LEGACY_MAP[value], illegal: false }
  return { key: value, illegal: true }
}

export const displaySlash = (slash?: string | null): string | null => {
  const raw = (slash || '').trim()
  if (!raw) return null
  return raw.startsWith('/') ? raw : `/${raw}`
}

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

export type MarketFilterValues = {
  type: string
  q: string
  host: string
  category: string
}

export const hasActiveFilters = (opts: MarketFilterValues): boolean => {
  if (opts.type && opts.type !== 'all') return true
  return Boolean(opts.q || opts.host || opts.category)
}

const FILTER_ECHO_LABELS: Record<'type' | 'q' | 'host' | 'category', string> = {
  type: '类型',
  q: '关键词',
  host: '宿主',
  category: '分类',
}

/** 筛空态回显当前 URL 筛（type/q/host/category 原值）。 */
export const activeFilterEcho = (
  opts: MarketFilterValues,
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
