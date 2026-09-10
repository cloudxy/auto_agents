/**
 * 系统配置 service（工单 71 归一）：/configs 站点配置键值对
 */
import api, { unwrap } from './api'

export const fetchSiteConfigs = (): Promise<Record<string, unknown>> =>
  api.get('/configs/').then((r) => unwrap<Record<string, unknown>>(r) ?? {})

export const updateSiteConfig = (key: string, value: unknown): Promise<void> =>
  api.put(`/configs/${key}`, { value }).then(() => undefined)

export interface WebhookStatus {
  secret_configured: boolean
  notify_webhook_url_configured: boolean
  dingtalk_configured: boolean
  wechat_work_configured: boolean
  env_override_active: boolean
}

/** Webhook 配置状态（只读；密钥仅配置态布尔，不回显值） */
export const fetchWebhookStatus = (): Promise<WebhookStatus> =>
  api.get('/admin/webhook-status').then((r) => unwrap<WebhookStatus>(r))
