/**
 * 能力广场公开 service（工单 71 归一）
 */
import api, { unwrap } from './api'
import type { PublicAsset } from '@auto-agents/frontend-shared'

export const listPublicAssets = (type: string): Promise<{ items: PublicAsset[] }> =>
  api.get('/public/capabilities', { params: { type, page_size: 50 } })
    .then((r) => unwrap<{ items: PublicAsset[] }>(r))
