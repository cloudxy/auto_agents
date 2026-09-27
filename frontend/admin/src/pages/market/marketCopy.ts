/** T-28 治理台七叶冻结句。listed ≠ verify ≠ 启用到宿主。 */

export const TABS = [
  { key: 'sources', label: '源' },
  { key: 'catalog', label: '目录' },
  { key: 'plugins', label: '插件' },
  { key: 'skills', label: '技能' },
  { key: 'commands', label: '命令' },
  { key: 'agents', label: '智能体' },
  { key: 'teams', label: '专家团' },
] as const

export const TAB_LABELS = TABS.map((t) => t.label)

export const LISTING_OPTIONS = [
  { value: 'unlisted', label: '未上架' },
  { value: 'listed', label: '已上架' },
  { value: 'coming_soon', label: '预告' },
] as const

export const NEED_PLATFORM_MARKET = '需要平台市场权限'
export const NEED_PLATFORM_ADMIN = '需要平台管理员'
export const MERGED = '已合并，不可上架'
export const BULK_LIST = '上架全部子资产'
export const ENABLE_HOST = '启用到宿主'
export const HOST_RUNNING = '已在你的宿主里运行'
export const SUB_NE_HOST = '订阅不等于已在宿主运行'
export const SUB_NE_HOST_DETAIL = '订阅只在本企业记下安装行。Wave 1 不会把能力写进宿主，也不会在你的机器上启用。'
export const LISTED_NE_VERIFY = '上架不等于验证通过'
export const SOURCE_EMPTY = '还没有源。登记源后才能同步。'
export const REGISTER_SOURCE = '登记源'
export const SOURCE_NOT_READY = '源登记尚未开放' // T-29 已开放；保留给旧快照
export const CATALOG_EMPTY = '还没有目录项。同步源或扫描后会出现在这里。'
export const COMMAND_EMPTY = '还没有命令。同步源或在目录登记后会出现在这里。'
export const AGENT_EMPTY = '还没有智能体。同步源或扫描后会出现在这里。'
export const TEAM_EMPTY = '还没有专家团。'
export const CREATE_TEAM = '组建专家团'
/** T-37（GWT-101.4）：成员选择器智能体分组空态句（无 agent 资产仍可纯专家组建） */
export const TEAM_AGENT_EMPTY = '还没有智能体资产'
export const GO_SOURCE = '去源叶'
export const HEALTH_UNKNOWN = '未知'
export const HEALTH_UNAVAILABLE = '不可用'
export const OPEN_IN_CATALOG = '在目录中打开'
export const LIST_CHILD = '单独上架'
export const GOVERNANCE_PAGE_SIZE = 20
export const GOVERNANCE_PAGINATION = {
  pageSize: GOVERNANCE_PAGE_SIZE,
  showSizeChanger: false,
  hideOnSinglePage: false,
  showTotal: (total: number) => `共 ${total} 条`,
} as const

export const catalogFocusCopy = (name: string): string => `已定位短名 ${name}`
export const VERIFY = '验证'
export const DETAIL = '详情'

/** T-02（FR-01，edge-states §7.6 钉句）：同步 .agents 四态文案 */
export const SYNC_AGENTS = '同步 .agents'
export const SYNCING = '同步中…'
export const syncDoneCopy = (added: number, updated: number, unchanged: number): string =>
  `同步完成：新增 ${added} · 更新 ${updated} · 无变化 ${unchanged}`
/** 失败句的后半段是非破坏语义的用户可见承诺（FR-01 信任修复点），不可删 */
export const syncFailCopy = (reason: string): string =>
  `同步失败：${reason}。已有数据未受影响。`

export const thirdPartyConfirm = (name: string): string =>
  `将把第三方「${name}」标为已上架，商店会对访客可见。确认上架？`

export const loadFail = (leaf: string): string => `${leaf}加载失败。检查网络后重试。`

export const healthLabel = (health?: string, hasMcp?: boolean): string => {
  if (!health || health === 'unknown') return HEALTH_UNKNOWN
  if (health === 'healthy') return '健康'
  if (hasMcp) return HEALTH_UNAVAILABLE
  return HEALTH_UNKNOWN
}

export const listingLabel = (state?: string): string => {
  const hit = LISTING_OPTIONS.find((o) => o.value === state)
  return hit ? hit.label : '未上架'
}
