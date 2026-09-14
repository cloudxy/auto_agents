/**
 * 平台网关钥匙（LiteLLM Admin /litellm/keys）。只给值班页「钥匙」叶消费。
 */
import api, { unwrap } from './api'

export interface LitellmKeyRow {
  key_alias?: string | null
  token?: string | null
  max_budget?: number | null
  spend?: number | null
  key?: string | null
}

export const listLitellmKeys = (): Promise<LitellmKeyRow[]> =>
  api.get('/litellm/keys').then((r) => unwrap<LitellmKeyRow[]>(r) ?? [])

export const createLitellmKey = (key_alias: string): Promise<LitellmKeyRow> =>
  api.post('/litellm/keys', { key_alias }).then((r) => unwrap<LitellmKeyRow>(r))
