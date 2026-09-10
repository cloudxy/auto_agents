/**
 * 超管产品事实查询（FR-15）。租户无此面。
 */
import api, { unwrap } from './api'

export interface ProductEventRow {
  id: number
  occurred_at: string
  event_name: string
  tenant_id: number | null
  actor_user_id: number | null
  anonymous_id: string | null
  role: string | null
  props: Record<string, unknown> | null
  created_at: string
}

export interface ProductEventList {
  total: number
  items: ProductEventRow[]
  timezone: string
}

export const listProductEvents = (params: {
  event_name?: string
  tenant_id?: number
}): Promise<ProductEventList> =>
  api.get('/product-events', { params }).then((r) => unwrap<ProductEventList>(r))
