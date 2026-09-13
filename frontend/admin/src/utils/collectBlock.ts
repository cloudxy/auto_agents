import {
  PLAN_FULL_COPY,
  SPIDER_WORKER_OFFLINE_CODE,
  STORAGE_CTA,
  TASK_QUOTA_LIMIT_CODE,
  UPGRADE_CTA,
} from '../constants/collectCopy'

export type CollectBlock =
  | { kind: 'worker' }
  | { kind: 'quota'; cta: string; dimension?: string }

interface EnvelopeLike {
  response?: {
    data?: {
      code?: string
      message?: string
      data?: { cta?: string; dimension?: string }
    }
  }
}

export function apiErrorCode(e: unknown): string {
  if (typeof e !== 'object' || e === null) return ''
  return (e as EnvelopeLike).response?.data?.code || ''
}

export function parseCollectBlock(e: unknown): CollectBlock | null {
  const code = apiErrorCode(e)
  if (code === SPIDER_WORKER_OFFLINE_CODE) return { kind: 'worker' }
  if (code === TASK_QUOTA_LIMIT_CODE) {
    const payload = (e as EnvelopeLike).response?.data?.data
    const cta = payload?.cta === STORAGE_CTA ? STORAGE_CTA : UPGRADE_CTA
    return { kind: 'quota', cta, dimension: payload?.dimension }
  }
  return null
}

export function quotaTitle(): string {
  return PLAN_FULL_COPY
}
