/**
 * LLM 供应商管理服务 - /llm/providers 端点封装（阶段二）
 *
 * 响应为后端 ApiResponse 统一信封（ADR-001），service 层统一解包 data，
 * 页面组件拿到的仍是裸结构（数组/对象），与 api.ts 的 unwrap 帮手配合。
 * api_key 仅创建时必填；更新时可选，留空表示不修改。列表返回脱敏值 api_key_masked。
 */
import api, { unwrap } from './api'

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
export interface LlmProviderModelEntry {
  model_id: string
  alias?: string
  model_tier?: 'strong' | 'basic'
  priority?: number
  is_default?: boolean
  enabled?: boolean
}

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
  /** B-M2 向导流：创建时一并落模型子表（默认模型取 is_default 行） */
  models?: LlmProviderModelEntry[]
}

/** 连通性测试结果 */
export interface LlmTestResult {
  ok: boolean
  latency_ms?: number | null
  model?: string | null
  error?: string | null
}

/** 供应商列表（信封 data=[...]） */
export const fetchLlmProviders = (): Promise<LlmProvider[]> =>
  api.get('/llm/providers').then((res) => unwrap<LlmProvider[]>(res))

/** 当前激活供应商（未激活时 404 → 上层 catch；未包装 null） */
export const fetchActiveLlmProvider = (): Promise<LlmProvider | null> =>
  api.get('/llm/providers/active').then((res) => unwrap<LlmProvider | null>(res))

/** 创建供应商 */
export const createLlmProvider = (payload: LlmProviderPayload): Promise<LlmProvider> =>
  api.post('/llm/providers', payload).then((res) => unwrap<LlmProvider>(res))

/** 更新供应商（api_key 留空不传表示不修改） */
export const updateLlmProvider = (id: number, payload: LlmProviderPayload): Promise<LlmProvider> =>
  api.put(`/llm/providers/${id}`, payload).then((res) => unwrap<LlmProvider>(res))

/** 删除供应商（信封 data 返回删除结果，前端删除后统一刷新列表） */
export const deleteLlmProvider = (id: number): Promise<unknown> =>
  api.delete(`/llm/providers/${id}`).then((res) => unwrap<unknown>(res))

/** 激活供应商（同一时刻仅一个激活；激活后统一刷新列表） */
export const activateLlmProvider = (id: number): Promise<unknown> =>
  api.put(`/llm/providers/${id}/activate`).then((res) => unwrap<unknown>(res))

/** 取消激活（全部下线：运行时解析回退 yml/env 兜底；行保留可再激活） */
export const deactivateLlmProvider = (id: number): Promise<LlmProvider> =>
  api.put(`/llm/providers/${id}/deactivate`).then((r) => unwrap<LlmProvider>(r))

/** 连通性测试（信封 data={ok, latency_ms, model, error}；可能较慢，单独放宽超时到 30s） */
export const testLlmProvider = (id: number): Promise<LlmTestResult> =>
  api
    .post(`/llm/providers/${id}/test`, undefined, { timeout: 30000 })
    .then((res) => unwrap<LlmTestResult>(res))

// ---------------- B-M1/M2：探测与多模型管理 ----------------

export interface PlatformPreset {
  name: string
  protocol: 'openai_compatible' | 'anthropic' | 'google_gemini'
  base_url: string
  requires_key: boolean
}

export interface ProbeModel {
  id: string
  owned_by: string
}

export const getPlatformPresets = (): Promise<PlatformPreset[]> =>
  api.get('/llm/providers/platform-presets').then((r) => unwrap<PlatformPreset[]>(r))

export const probeModels = (payload: {
  provider_type: string
  base_url: string
  api_key: string
}): Promise<{ models: ProbeModel[]; chat_only_count: number }> =>
  api.post('/llm/providers/models/probe', payload).then((r) => unwrap(r))

export const probeTest = (payload: {
  provider_type: string
  base_url: string
  api_key: string
  model: string
}): Promise<{ ok: boolean; latency_ms: number; model: string; error: string }> =>
  api.post('/llm/providers/models/probe-test', payload).then((r) => unwrap(r))

export interface ProviderModelRow {
  model_id: string
  alias: string
  model_tier: 'strong' | 'basic'
  priority: number
  is_default: boolean
  enabled: boolean
  health_status: 'unknown' | 'healthy' | 'degraded' | 'down'
  last_checked_at?: string | null
  last_latency_ms?: number | null
}

export const getLlmProviderModels = (providerId: number): Promise<ProviderModelRow[]> =>
  api.get(`/llm/providers/${providerId}/models`).then((r) => unwrap<ProviderModelRow[]>(r))

export const putLlmProviderModels = (
  providerId: number,
  models: Array<Pick<ProviderModelRow, 'model_id' | 'alias' | 'model_tier' | 'priority' | 'is_default' | 'enabled'>>,
): Promise<ProviderModelRow[]> =>
  api.put(`/llm/providers/${providerId}/models`, { models }).then((r) => unwrap<ProviderModelRow[]>(r))

export const fetchModelsDiff = (
  providerId: number,
): Promise<{ new: string[]; existing: string[]; vanished: string[] }> =>
  api.post(`/llm/providers/${providerId}/models/fetch`).then((r) => unwrap(r))

export const testLlmProviderModel = (
  providerId: number,
  modelId: string,
): Promise<{ ok: boolean; latency_ms: number; model: string; error: string; health_status: string }> =>
  api.post(`/llm/providers/${providerId}/models/${encodeURIComponent(modelId)}/test`).then((r) => unwrap(r))
