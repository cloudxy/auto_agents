/**
 * 租户成员域 service（SaaS S2，工单 71 归一）
 */
import api, { unwrap } from './api'

export interface MemberRow {
  id: number
  username: string
  email: string
  tenant_role: string
  is_active: boolean
  created_at?: string | null
}

export const listMembers = (): Promise<MemberRow[]> =>
  api.get('/members').then((r) => unwrap<MemberRow[]>(r))

export const createMember = (payload: Record<string, unknown>): Promise<MemberRow> =>
  api.post('/members', payload).then((r) => unwrap<MemberRow>(r))

export const patchMember = (id: number, payload: Record<string, unknown>): Promise<MemberRow> =>
  api.patch(`/members/${id}`, payload).then((r) => unwrap<MemberRow>(r))

export const resetMemberPassword = (id: number, newPassword: string): Promise<void> =>
  api.post(`/members/${id}/reset-password`, { new_password: newPassword }).then(() => undefined)

export interface MemberAuditRow {
  id: number
  actor_name: string
  action: string
  target: string
  detail: string | null
  created_at: string | null
}

/** 成员操作审计·租户视角（B6 工单 91） */
export const listMemberAudit = (limit = 50): Promise<MemberAuditRow[]> =>
  api.get('/members/audit', { params: { limit } }).then((r) => unwrap<MemberAuditRow[]>(r))
