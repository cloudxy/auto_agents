/** T-26 我的安装冻结句。空 ≠ 加载失败。两句只读不得混用。 */

export const EMPTY_COPY = '还没有安装'
export const EMPTY_CTA = '去能力市场'
export const LOAD_FAIL = '安装列表加载失败。检查网络后重试。'
export const OFFLINE_UNINSTALL = '网络不可用，安装行没有删除。'
export const READONLY_ROLE = '当前账号不能改安装。请联系企业管理员。'
export const READONLY_UNINSTALL_TIP = '当前账号不能卸载'
export const DELISTED = '已下架'
export const DELISTED_RESUBSCRIBE = '已下架，不能新订'
export const TRUST_CONFIRM = '打开信任后，按该能力的说明在宿主里使用。平台不会改你的本机配置。'
export const NEEDS_TENANT = '需要企业空间才能订阅'
export const FORBIDDEN_RUNTIME = '已在你的宿主里运行'
export const ENABLE_HOST = '启用到宿主'

export const COPY_BY_CODE: Record<string, string> = {
  MARKET_READONLY_ROLE: READONLY_ROLE,
  MARKET_NEEDS_TENANT: NEEDS_TENANT,
}

export const GROUP_ORDER = ['skill', 'plugin', 'command', 'agent', 'team'] as const
export const GROUP_LABELS: Record<string, string> = {
  skill: '技能',
  plugin: '插件',
  command: '命令',
  agent: '智能体',
  team: '专家团',
}

export const HOST_LABELS: Record<string, string> = {
  grok: 'Grok', zcode: 'ZCode', kimi: 'Kimi', claude: 'Claude',
}

export const publicType = (raw: string): string => {
  if (raw === 'expert') return 'agent'
  if (raw === 'expert_team') return 'team'
  return raw
}

export const uninstallConfirm = (row: { asset_type: string; asset_name: string; host: string }): string => {
  const host = HOST_LABELS[row.host] || row.host
  if (publicType(row.asset_type) === 'plugin') {
    return `卸载插件「${row.asset_name}」在 ${host} 的安装？其中的技能不会一并卸载。`
  }
  return `卸载「${row.asset_name}」在 ${host} 的安装？`
}

export const uninstallFail = (reason: string): string => `卸载失败。${reason}。重试。`

type ApiErr = { response?: { data?: { code?: string; message?: string } }; message?: string }

export const errorCode = (e: unknown): string | undefined => {
  if (typeof e !== 'object' || e === null) return undefined
  return (e as ApiErr).response?.data?.code
}

export const loadErrorCopy = (e: unknown): string => {
  const code = errorCode(e)
  if (code && COPY_BY_CODE[code]) return COPY_BY_CODE[code]
  return LOAD_FAIL
}

export const uninstallErrorCopy = (e: unknown): string => {
  const code = errorCode(e)
  if (code === 'MARKET_READONLY_ROLE') return READONLY_ROLE
  const offline = typeof navigator !== 'undefined' && navigator.onLine === false
  const noResp = typeof e === 'object' && e !== null && !(e as ApiErr).response
  if (offline || noResp) return OFFLINE_UNINSTALL
  const reason = (e as ApiErr).response?.data?.message || '请稍后重试'
  return uninstallFail(reason)
}
