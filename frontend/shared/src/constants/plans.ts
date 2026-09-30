/**
 * 价目展示（审计 F1-1：定价单一来源）
 *
 * 官网定价页、admin 结账页的价格一律读 `/billing/plans`（后端 plans 表），前端不再手抄金额；
 * 本文件只负责把后端价目格式化成展示文案。
 */

/** `/billing/plans` 返回的公开价目行（与后端 PlanOut 同形） */
export interface PublicPlan {
  id: number
  slug: string
  name: string
  price_cents: number
  period: string
  quota_json?: string | null
  is_public: number
  /** 按需定制、走「联系我们」（决策 D17），不能自助结账 */
  sales_led?: boolean
}

/** 分 → 「¥299」「¥2,990」「¥0.5」；免费档返回「¥0」 */
export function formatYuan(priceCents: number): string {
  const yuan = Math.max(0, Number(priceCents) || 0) / 100
  const text = Number.isInteger(yuan)
    ? yuan.toLocaleString('en-US')
    : yuan.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return `¥${text}`
}

/** 价目 → 「¥299/月」「¥2,990/年」；免费档只显示「¥0」 */
export function formatPlanPrice(plan: Pick<PublicPlan, 'price_cents' | 'period'>): string {
  if (!plan.price_cents) return '¥0'
  const unit = plan.period === 'year' ? '年' : '月'
  return `${formatYuan(plan.price_cents)}/${unit}`
}
