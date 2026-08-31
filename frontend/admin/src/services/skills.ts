/**
 * 技能管理中心服务封装 - /skills 端点（方案 A）
 *
 * 响应为后端统一信封（ADR-001）；service 层统一解包 data。
 */
import api, { unwrap } from './api'

export interface SkillItem {
  id: number
  name: string
  title: string
  description?: string | null
  category: string
  industries?: string[] | null
  status: string
  source_type: string
  source_url?: string
  tier?: string | null
  score?: number | null
  ai_suggested_score?: number | null
  reviewed_by?: string | null
  similar_to?: string[] | null
  sync_state: string
  updated_at?: string | null
}

export interface SkillReviewItem {
  id: number
  reviewer_type: 'ai' | 'human'
  reviewer: string
  score?: number | null
  rubric?: Record<string, number> | null
  notes?: string | null
  prompt_version?: string | null
  created_at?: string | null
}

export interface SkillDetail extends SkillItem {
  rubric_human?: Record<string, number> | null
  rubric_ai?: Record<string, number> | null
  review_notes?: string | null
  content_hash?: string
  file_path?: string
  skill_md?: string | null
  meta_yaml?: string | null
  reviews: SkillReviewItem[]
}

export interface SkillListParams {
  q?: string
  category?: string
  status?: string
  tier?: string
  source_type?: string
  sort?: string
  page?: number
  page_size?: number
}

export interface SkillListResult {
  total: number
  items: SkillItem[]
}

export interface ScanSummary {
  total: number
  succeeded: number
  failed: number
  failed_names: string[]
  missing: string[]
  job_id: number
}

export const listSkills = (params: SkillListParams): Promise<SkillListResult> =>
  api.get('/skills', { params }).then((r) => unwrap<SkillListResult>(r.data))

export const getSkillDetail = (name: string): Promise<SkillDetail> =>
  api.get(`/skills/${encodeURIComponent(name)}`).then((r) => unwrap<SkillDetail>(r.data))

export const scanSkills = (): Promise<ScanSummary> =>
  api.post('/skills/scan').then((r) => unwrap<ScanSummary>(r.data))

export interface CorrectionPayload {
  category?: string
  status?: string
  similar_to?: string[]
  score?: number
  rubric_human?: Record<string, number>
  review_notes?: string
}

export const correctSkillMeta = (name: string, payload: CorrectionPayload): Promise<{
  name: string
  written_back: boolean
  tier: string | null
}> =>
  api.put(`/skills/${encodeURIComponent(name)}/meta`, payload).then((r) => unwrap(r.data))
