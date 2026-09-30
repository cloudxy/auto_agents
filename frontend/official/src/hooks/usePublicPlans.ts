/**
 * 读公开价目；失败不抛错（页面降级为「以结账页为准」），不依赖 QueryClientProvider
 */
import { useEffect, useState } from 'react'
import type { PublicPlan } from '@auto-agents/frontend-shared'
import { fetchPublicPlans } from '../services/billing'

export type PlansState = { plans: PublicPlan[]; loading: boolean; failed: boolean }

export function usePublicPlans(): PlansState {
  const [state, setState] = useState<PlansState>({ plans: [], loading: true, failed: false })
  useEffect(() => {
    let alive = true
    fetchPublicPlans()
      .then((plans) => { if (alive) setState({ plans: plans || [], loading: false, failed: false }) })
      .catch(() => { if (alive) setState({ plans: [], loading: false, failed: true }) })
    return () => { alive = false }
  }, [])
  return state
}
