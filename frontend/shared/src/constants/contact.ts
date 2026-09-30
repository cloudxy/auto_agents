/**
 * 对外联系（决策 D25：联系与提醒走邮箱，写明响应时效）
 * 数据来自后端 GET /public/ops-contact（OPS.CONTACT_EMAIL / OPS.CONTACT_SLA），前端不手抄。
 */
export interface PublicContact {
  duty_contact: string
  contact_email: string
  contact_sla: string
}

/** 联系邮件链接；没配置联系邮箱时退回值班联系；都没有返回 null（前端据此降级展示） */
export function contactMailto(contact: PublicContact | null | undefined, subject?: string): string | null {
  const email = (contact?.contact_email || contact?.duty_contact || '').trim()
  if (!email) return null
  return `mailto:${email}${subject ? `?subject=${encodeURIComponent(subject)}` : ''}`
}
