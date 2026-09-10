/**
 * 死信队列 service（B6 工单 91）：结果回流死信的查看/丢弃/清空
 */
import api, { unwrap } from './api'

export interface DeadItem {
  seq: number
  index: number
  raw: string
  spider_name?: string | null
  payload: Record<string, unknown> | null
}

export const listDeadItems = (limit = 100): Promise<{ total: number; items: DeadItem[] }> =>
  api.get('/admin/dead-items', { params: { limit } }).then((r) => unwrap<{ total: number; items: DeadItem[] }>(r))

export const discardDeadItem = (index: number): Promise<void> =>
  api.delete(`/admin/dead-items/${index}`).then(() => undefined)

export const clearDeadItems = (): Promise<{ removed: number }> =>
  api.delete('/admin/dead-items').then((r) => unwrap<{ removed: number }>(r))
