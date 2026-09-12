/**
 * 免费档默认配额。与 backend `quota_service.DEFAULT_QUOTA` 同数。
 * 官网定价文案与用量页 mock 必须读这里，避免 GWT-01.1 数字漂移。
 */

export const DEFAULT_QUOTA = {
  task_concurrency: 5,
  result_storage: 10000,
  llm_tokens_month: 200000,
} as const

export type DefaultQuota = typeof DEFAULT_QUOTA

/** 官网定价免费档三条（闭集 A；不得标预告）。 */
export const FREE_TIER_FEATURE_COPY = {
  task_concurrency: `${DEFAULT_QUOTA.task_concurrency} 个并发任务`,
  result_storage: `${DEFAULT_QUOTA.result_storage.toLocaleString('en-US')} 条结果存储`,
  llm_tokens_month: `${DEFAULT_QUOTA.llm_tokens_month / 10000} 万 LLM tokens/月`,
} as const

/**
 * 专业档配额（T-03 / GWT-50.13 一套真相）：与官网定价页专业档三条同数。
 * 用量页 QA-23 夹具（企业已按专业档执法）必须读这里，不得手抄第二套数字。
 * 注意：官网 Pricing.tsx 本波冻结（Q-PRICE），专业档三条仍为其页内字面——
 * 本常量按同 deriv 规则生成，由 Usage 测试钉字面相等（漂移即红）。
 */
export const PRO_TIER_QUOTA = {
  task_concurrency: 50,
  result_storage: 200000,
  llm_tokens_month: 5000000,
} as const

export type ProTierQuota = typeof PRO_TIER_QUOTA

/** 官网定价专业档三条（闭集 B；预告不可购买——Q-PRICE：不撤 ¥299、不写当前可买）。 */
export const PRO_TIER_FEATURE_COPY = {
  task_concurrency: `${PRO_TIER_QUOTA.task_concurrency} 个并发任务`,
  result_storage: `${PRO_TIER_QUOTA.result_storage.toLocaleString('en-US')} 条结果存储`,
  llm_tokens_month: `${PRO_TIER_QUOTA.llm_tokens_month / 10000} 万 LLM tokens/月`,
} as const
