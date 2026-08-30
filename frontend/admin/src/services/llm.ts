/**
 * LLM 供应商管理服务 - /llm/providers 端点封装（阶段二）
 *
 * 响应为后端 Pydantic 直出（无 ApiResponse 信封），与 services/ai.ts 解包方式一致。
 * api_key 仅创建时必填；更新时可选，留空表示不修改。列表返回脱敏值 api_key_masked。
 */
import api from './api'

/** LLM 供应商配置 */
export interface LlmProvider {
  id: number
  name: string
  provider_type?: string | null
  base_url: string
  model: string
  temperature?: number | null
  timeout?: number | null
  max_retries?: number | null
  /** 是否为当前激活供应商（同一时刻至多一个） */
  is_active: boolean
  /** 是否启用（停用后不参与调度） */
  enabled: boolean
  remark?: string | null
  /** 脱敏后的 API Key（如 sk-***abc），用于编辑态 placeholder 展示 */
  api_key_masked?: string | null
  created_at?: string | null
  updated_at?: string | null
}

/** 创建/更新供应商入参（api_key 更新时可选：留空表示不修改） */
export interface LlmProviderPayload {
  name: string
  provider_type?: string | null
  base_url: string
  api_key?: string
  model: string
  temperature?: number | null
  timeout?: number | null
  max_retries?: number | null
  enabled?: boolean
  remark?: string | null
}

/** 连通性测试结果 */
export interface LlmTestResult {
  ok: boolean
  latency_ms?: number | null
  model?: string | null
  error?: string | null
}

/** 供应商列表 */
export const fetchLlmProviders = (): Promise<LlmProvider[]> => {
  return api.get('/llm/providers') as unknown as Promise<LlmProvider[]>
}

/** 当前激活供应商（未激活时为 null） */
export const fetchActiveLlmProvider = (): Promise<LlmProvider | null> => {
  return api.get('/llm/providers/active') as unknown as Promise<LlmProvider | null>
}

/** 创建供应商 */
export const createLlmProvider = (payload: LlmProviderPayload): Promise<LlmProvider> => {
  return api.post('/llm/providers', payload) as unknown as Promise<LlmProvider>
}

/** 更新供应商（api_key 留空不传表示不修改） */
export const updateLlmProvider = (id: number, payload: LlmProviderPayload): Promise<LlmProvider> => {
  return api.put(`/llm/providers/${id}`, payload) as unknown as Promise<LlmProvider>
}

/** 删除供应商（返回体契约未明确，前端不依赖返回值，删除后统一刷新列表） */
export const deleteLlmProvider = (id: number): Promise<unknown> => {
  return api.delete(`/llm/providers/${id}`) as unknown as Promise<unknown>
}

/** 激活供应商（同一时刻仅一个激活；返回体契约未明确，前端激活后统一刷新列表） */
export const activateLlmProvider = (id: number): Promise<unknown> => {
  return api.put(`/llm/providers/${id}/activate`) as unknown as Promise<unknown>
}

/** 连通性测试（可能较慢，单独放宽超时到 30s，避免实例默认 10s 误判失败） */
export const testLlmProvider = (id: number): Promise<LlmTestResult> => {
  return api.post(`/llm/providers/${id}/test`, undefined, { timeout: 30000 }) as unknown as Promise<LlmTestResult>
}
