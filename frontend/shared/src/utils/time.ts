/**
 * 接口时间的展示（审计 BUG-43）。
 *
 * 后端约定：库里存 UTC，出参是带偏移的 ISO 串（`2026-09-14T01:03:03+00:00`）。
 * 展示统一按业务时区 Asia/Shanghai，不依赖浏览器所在时区；
 * 个别历史 JSON 里没有偏移的串按 UTC 解释（与后端约定一致），不按浏览器本地时间解释。
 */
export const BUSINESS_TZ = 'Asia/Shanghai'

const NAIVE_ISO = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/

/** 解析接口时间；无法解析返回 null */
export function parseApiTime(value?: string | null): Date | null {
  if (!value) return null
  const text = NAIVE_ISO.test(value) ? `${value.replace(' ', 'T')}Z` : value
  const d = new Date(text)
  return Number.isNaN(d.getTime()) ? null : d
}

const partsFormatter = new Intl.DateTimeFormat('en-CA', {
  timeZone: BUSINESS_TZ,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  // lib 目标较老，类型里没有 hourCycle；运行时各引擎都支持
  hourCycle: 'h23',
} as Intl.DateTimeFormatOptions)

function parts(d: Date): Record<string, string> {
  const out: Record<string, string> = {}
  for (const p of partsFormatter.formatToParts(d)) out[p.type] = p.value
  if (out.hour === '24') out.hour = '00' // 个别引擎午夜给 24
  return out
}

/** `2026-09-14 09:03:03`（北京时间）；空值 / 不可解析返回 fallback */
export function formatDateTime(value?: string | null, fallback = '-'): string {
  const d = parseApiTime(value)
  if (!d) return value ? value : fallback
  const p = parts(d)
  return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}:${p.second}`
}

/** `2026-09-14`（北京时间的日期）；空值 / 不可解析返回 fallback */
export function formatDate(value?: string | null, fallback = '-'): string {
  const d = parseApiTime(value)
  if (!d) return value ? value : fallback
  const p = parts(d)
  return `${p.year}-${p.month}-${p.day}`
}
