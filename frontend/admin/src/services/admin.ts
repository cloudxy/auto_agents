/**
 * 平台管理域 service（工单 71）：admin 专属端点（统计/用户/审计日志）
 * 统一解包信封，页面不再裸调 api。
 */
import api, { unwrap } from './api'

/** GET /admin/stats（工作台与数据中心共用，字段形状由调用方泛型指定） */
export const fetchAdminStats = <T,>(): Promise<T> =>
  api.get('/admin/stats').then((r) => unwrap<T>(r))

/** 最近完成的任务 ID 列表（工作台质量报告入口） */
export const fetchRecentCompletedTasks = (limit = 5): Promise<number[]> =>
  api.get('/spiders/tasks', { params: { status: 'completed', limit } })
    .then((r) => unwrap<{ items: { id: number }[] }>(r))
    .then((d) => (d.items || []).map((t) => t.id))

/** GET /spiders/tasks/{id}/quality */
export const fetchQualityReport = <T,>(taskId: number): Promise<T> =>
  api.get(`/spiders/tasks/${taskId}/quality`).then((r) => unwrap<T>(r))

/** GET /admin/users（平台超管用户分页；status=deleted 为「已删除」筛选，T-24/FR-93） */
/** GET /admin/users：筛选全部在服务端（决策 D11），total 与筛选一致 */
export interface UsersPageQuery {
  skip: number
  limit: number
  /** active=在职（含停用）；enabled=在职·激活；disabled=已停用；deleted=已删除 */
  status?: 'active' | 'enabled' | 'disabled' | 'deleted'
  /** 登录名或邮箱包含 */
  q?: string
  role?: string
  tenant_id?: number
  department_id?: number
}
export const fetchUsersPage = <T,>(params: UsersPageQuery): Promise<{ items: T[]; total: number }> =>
  api.get('/admin/users', { params }).then((r) => unwrap<{ items: T[]; total: number }>(r))

/** GET /admin/audit-logs（操作审计分页） */
export interface AuditLogsQuery {
  skip?: number
  limit?: number
  user?: string
  action?: string
  start_time?: string
  end_time?: string
}
export const fetchAuditLogs = <T,>(params: AuditLogsQuery): Promise<{ items: T[]; total: number }> =>
  api.get('/admin/audit-logs', { params }).then((r) => unwrap<{ items: T[]; total: number }>(r))

/** GET /spiders/nodes（Worker 节点分页） */
export const fetchNodesPage = <T,>(): Promise<{ items: T[]; total: number }> =>
  api.get('/spiders/nodes').then((r) => unwrap<{ items: T[]; total: number }>(r))
