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
