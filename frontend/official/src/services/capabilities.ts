/**
 * 能力市场公开 service（T-21 列表；T-22 筛；T-24 详情；T-14 翻页 + 翻页埋点身份）
 */
import api, { unwrap } from './api'
import { ensureAnonymousId } from './beacon'
import type { PublicAsset } from '@auto-agents/frontend-shared'

export type { PublicAsset }

/** 出处：仅父插件已上架时才带 href（T-23 不给未上架父的可点字段） */
export type PublicOrigin = {
  name?: string | null
  title?: string | null
  asset_type?: string | null
  href?: string | null
}

export type PublicInclude = {
  asset_type: string
  name: string
  title?: string | null
  listing_state?: string | null
}

export type PublicListItem = PublicAsset & {
  listing_state?: string | null
  subscribable?: boolean
  hosts?: string[]
  slash?: string | null
}

export type PublicAssetDetail = PublicListItem & {
  license?: string | null
  source_author?: string | null
  source_url?: string | null
  includes?: PublicInclude[]
  skill_md?: string | null
  body_md?: string | null
  origin?: PublicOrigin | null
  origin_plugin_name?: string | null
  status?: string | null
}

export type PublicListQuery = {
  type?: string
  q?: string
  host?: string
  category?: string
  page?: number
  page_size?: number
}

/** 后端 /public/* 列表统一分页形态（T-14：公开端 page_size 上限 20） */
export type PublicListResult = {
  items: PublicListItem[]
  total?: number
  page?: number
  page_size?: number
  has_more?: boolean
}

const compactQuery = (params: PublicListQuery): Record<string, string | number> => {
  const page = params.page ?? 1
  const query: Record<string, string | number> = {
    page_size: params.page_size ?? 20,
    page,
  }
  if (params.type) query.type = params.type
  if (params.q) query.q = params.q
  if (params.host) query.host = params.host
  if (params.category) query.category = params.category
  // GWT-92.5：翻页动作（第 2 页起）携带浏览会话 anonymous_id，
  // 后端在该请求上上报 market_list_paged（访客无 tenant_id）。
  if (page >= 2) query.anonymous_id = ensureAnonymousId()
  return query
}

export const listPublicAssets = (
  params: PublicListQuery = {},
): Promise<PublicListResult> =>
  api.get('/public/capabilities', { params: compactQuery(params) })
    .then((r) => unwrap<PublicListResult>(r))

export const getPublicAsset = (
  assetType: string,
  name: string,
): Promise<PublicAssetDetail> =>
  api.get(
    `/public/capabilities/${encodeURIComponent(assetType)}/${encodeURIComponent(name)}`,
  ).then((r) => unwrap<PublicAssetDetail>(r))
