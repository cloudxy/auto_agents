/**
 * 官网产品事件埋点（FR-15）。失败不挡浏览/注册。
 */
import api from './api'

const ANON_KEY = 'aa_anonymous_id'

export const CTA_FUNNEL = [
  'register_free',
  'pricing_pro',
  'pricing_enterprise',
  'login',
  'browse_market',
] as const

export type FunnelCta = (typeof CTA_FUNNEL)[number]
export type BypassCta = 'enter_admin' | 'try_ai_flow'

export function getAnonymousId(): string | null {
  try {
    return localStorage.getItem(ANON_KEY)
  } catch {
    return null
  }
}

export function ensureAnonymousId(): string {
  try {
    let id = localStorage.getItem(ANON_KEY)
    if (!id) {
      id = (typeof crypto !== 'undefined' && crypto.randomUUID)
        ? crypto.randomUUID()
        : `anon-${Date.now()}`
      localStorage.setItem(ANON_KEY, id)
    }
    return id
  } catch {
    return `anon-${Date.now()}`
  }
}

export function trackOfficial(eventName: string, props: Record<string, unknown>): void {
  const body = {
    event_name: eventName,
    anonymous_id: ensureAnonymousId(),
    props,
  }
  void api.post('/public/events', body).catch(() => {
    /* 上报失败不挡主路径 */
  })
}

export function trackPageView(page: string): void {
  trackOfficial('official_page_viewed', { page })
}

export function trackCta(cta: FunnelCta | BypassCta): void {
  trackOfficial('official_cta_clicked', { cta })
}
