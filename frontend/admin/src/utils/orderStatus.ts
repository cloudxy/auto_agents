/** W2 租户可见闭集：待支付 / 已开通。旧 pending/paid 读模型仍认识。 */

export const TENANT_PENDING = '待支付'
export const TENANT_FULFILLED = '已开通'

const FULFILLED = new Set(['fulfilled', 'paid'])

export function tenantOrderStatus(status: string | undefined): typeof TENANT_PENDING | typeof TENANT_FULFILLED {
  if (status && FULFILLED.has(status)) return TENANT_FULFILLED
  return TENANT_PENDING
}

export function isFulfilledStatus(status: string | undefined): boolean {
  return Boolean(status && FULFILLED.has(status))
}
