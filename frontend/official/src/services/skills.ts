/**
 * 技能广场公开 API 封装（方案 A · A-P4-2）
 * 官网无鉴权：调 /public/skills（后端三道闸：发布态/白名单/IP 限流）。
 * api 拦截器已剥 axios 层，此处拿到的是统一信封体，再解 data。
 */
import api from './api'

// 信封解包与公开类型单源在 shared（F-6）
import { unwrap, type PublicSkill } from '@auto-agents/frontend-shared'

export type { PublicSkill }

export const listPublicSkills = (params?: {
  q?: string
  category?: string
  page?: number
  page_size?: number
}): Promise<{ total: number; items: PublicSkill[] }> =>
  api.get('/public/skills', { params }).then((r) => unwrap<{ total: number; items: PublicSkill[] }>(r))

export const getPublicSkill = (name: string): Promise<PublicSkill> =>
  api.get(`/public/skills/${encodeURIComponent(name)}`).then((r) => unwrap<PublicSkill>(r))
