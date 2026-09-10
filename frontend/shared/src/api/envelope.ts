/**
 * 统一响应信封（与后端 ApiResponse / PaginatedResponse 对齐，ADR-001）
 *
 * 单一定义点（工单 66 / F-6）：admin 与 official 一律从这里 import，
 * 禁止在任何应用内重复声明 ApiEnvelope / Envelope 同构接口。
 */
export interface ApiEnvelope<T> {
  success: boolean
  code: string
  message: string
  data: T
  request_id?: string | null
}

/** 从信封中解出业务载荷（service 层统一出口） */
export const unwrap = <T,>(envelope: unknown): T =>
  (envelope as ApiEnvelope<T>).data

/** 分页载荷形状（PaginatedResponse.data） */
export interface PaginatedData<T> {
  items: T[]
  total: number
}
