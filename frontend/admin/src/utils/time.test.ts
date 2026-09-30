/**
 * 接口时间展示（审计 BUG-43）：出参是带偏移的 UTC，展示按北京时间，不看浏览器时区
 */
import { formatDate, formatDateTime, parseApiTime } from '@auto-agents/frontend-shared'

test('offset-aware UTC renders as Beijing time', () => {
  expect(formatDateTime('2026-09-14T01:03:03+00:00')).toBe('2026-09-14 09:03:03')
  expect(formatDateTime('2026-09-14T01:03:03Z')).toBe('2026-09-14 09:03:03')
})

test('crosses the date line at Beijing midnight', () => {
  // UTC 09-26 17:00 = 北京 09-27 01:00
  expect(formatDate('2026-09-26T17:00:00+00:00')).toBe('2026-09-27')
})

test('offset-less strings are UTC per the backend contract, not browser-local', () => {
  expect(formatDateTime('2026-09-14T01:03:03')).toBe('2026-09-14 09:03:03')
  expect(parseApiTime('2026-09-14 01:03:03')?.toISOString()).toBe('2026-09-14T01:03:03.000Z')
})

test('empty and unparsable values fall back', () => {
  expect(formatDateTime(null)).toBe('-')
  expect(formatDateTime(undefined, '—')).toBe('—')
  expect(formatDateTime('not-a-date')).toBe('not-a-date')
})
