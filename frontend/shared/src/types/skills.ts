/**
 * 手工共享类型（批次 1 过渡形态）
 *
 * 批次 3（工单 81）接入 OpenAPI codegen 后由
 * shared/src/api/schema.d.ts 生成类型替代，本文件届时退役。
 */

/** 技能/资产目录公共字段（治理视角，admin SkillItem 与 official PublicSkill 的公共子集） */
export interface SkillBase {
  id?: number
  name: string
  title: string
  description?: string | null
  category: string
  industries?: string[] | null
  tier?: string | null
  score?: number | null
  status: string
  source_url?: string | null
  source_author?: string | null
  updated_at?: string | null
}

/** 公开技能（GET /public/skills） */
export interface PublicSkill extends SkillBase {
  skill_md?: string | null
}

/** 公开能力资产（GET /public/capabilities） */
export interface PublicAsset {
  asset_type: string
  name: string
  title: string
  description?: string | null
  category: string
  tier?: string | null
  score?: number | null
}
