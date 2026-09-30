/** 对外联系（决策 D25）：后端 /public/ops-contact 单一来源 */
import type { PublicContact } from '@auto-agents/frontend-shared'
import api, { unwrap } from './api'

export const fetchPublicContact = (): Promise<PublicContact> =>
  api.get('/public/ops-contact').then((r) => unwrap<PublicContact>(r))
