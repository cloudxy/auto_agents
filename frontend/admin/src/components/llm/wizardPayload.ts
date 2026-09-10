import type { LlmProvider, LlmProviderPayload } from '../../services/llm'

type WizardValues = {
  name?: string
  provider_type?: string
  base_url?: string
  api_key?: string
  model?: string
  temperature?: number
  timeout?: number
  max_retries?: number
  enabled?: boolean
  remark?: string
  models_field?: string[]
}

export function resolveWizardModel(
  values: WizardValues,
  editing: LlmProvider | null,
): string {
  return String(values.model ?? editing?.model ?? '').trim()
}

export function buildWizardPayload(
  values: WizardValues,
  editing: LlmProvider | null,
): LlmProviderPayload | null {
  const model = resolveWizardModel(values, editing)
  if (!model) return null
  const payload: LlmProviderPayload = {
    name: String(values.name ?? '').trim(),
    provider_type: String(values.provider_type ?? '').trim() || 'openai_compatible',
    base_url: String(values.base_url ?? '').trim(),
    api_key: values.api_key?.trim() || undefined,
    model,
    temperature: values.temperature ?? undefined,
    timeout: values.timeout ?? undefined,
    max_retries: values.max_retries ?? undefined,
    enabled: values.enabled ?? true,
    remark: values.remark?.trim() || undefined,
  }
  if (!editing) {
    payload.models = (values.models_field || []).map((id) => ({
      model_id: id,
      is_default: id === model,
    }))
  }
  return payload
}
