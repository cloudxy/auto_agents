/**
 * 公开价目（审计 F1-1：定价单一来源 = 后端 /billing/plans）
 */
import type { PublicPlan } from '@auto-agents/frontend-shared'
import api, { unwrap } from './api'

export const fetchPublicPlans = (): Promise<PublicPlan[]> =>
  api.get('/billing/plans').then((r) => unwrap<PublicPlan[]>(r))
