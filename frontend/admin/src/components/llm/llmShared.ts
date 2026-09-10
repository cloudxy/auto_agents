/**
 * LLM 域共享常量（工单 80 拆分自 LlmProviders.tsx）
 */
export const PROTOCOL_NAMES: Record<string, string> = {
  openai_compatible: 'OpenAI 兼容', anthropic: 'Anthropic 原生', google_gemini: 'Google Gemini',
}

export const HEALTH_TAGS: Record<string, { color: string; label: string }> = {
  unknown: { color: 'default', label: '未测' },
  healthy: { color: 'success', label: '健康' },
  degraded: { color: 'warning', label: '降级' },
  down: { color: 'error', label: '不可用' },
}
