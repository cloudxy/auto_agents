/**
 * 技能广场公开 API 封装（方案 A · A-P4-2）
 * 官网无鉴权：调 /public/skills（后端三道闸：发布态/白名单/IP 限流）。
 * api 拦截器已剥 axios 层，此处拿到的是统一信封体，再解 data。
 */
import api from './api'

export interface PublicSkill {
  name: string
  title: string
  description?: string | null
  category: string
  industries?: string[] | null
  tier?: string | null
  score?: number | null
  status: string
  source_url?: string
  source_author?: string
  updated_at?: string | null
  skill_md?: string | null
}

interface Envelope<T> {
  success: boolean
  code: string
  message: string
  data: T
}

/** 拦截器运行时已剥 AxiosResponse 壳（类型声明仍是 AxiosResponse），unknown 收窄解包 */
const unwrap = <T,>(r: unknown): T => (r as Envelope<T>).data

export const listPublicSkills = (params?: {
  q?: string
  category?: string
  page?: number
  page_size?: number
}): Promise<{ total: number; items: PublicSkill[] }> =>
  api.get('/public/skills', { params }).then((r) => unwrap<{ total: number; items: PublicSkill[] }>(r))

export const getPublicSkill = (name: string): Promise<PublicSkill> =>
  api.get(`/public/skills/${encodeURIComponent(name)}`).then((r) => unwrap<PublicSkill>(r))
