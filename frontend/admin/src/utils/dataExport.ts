/**
 * 数据中心导出（T-02 / FR-M02）：CSV/JSON，100 行闸，超限无文件。
 */
import type { SpiderResult } from '../services/spiders'
import { EXPORT_MAX_ROWS } from '../constants/collectCopy'

export const resultsToCsv = (rows: SpiderResult[]): string => {
  const header = ['id', 'task_id', 'spider_name', 'title', 'content', 'url', 'created_at']
  const esc = (v: unknown) => {
    const s = v === null || v === undefined ? '' : String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const lines = [
    header.join(','),
    ...rows.map((r) => header.map((h) => esc((r as unknown as Record<string, unknown>)[h])).join(',')),
  ]
  return '\ufeff' + lines.join('\n')
}

export const nonCandidateRows = (rows: SpiderResult[]): SpiderResult[] =>
  rows.filter((r) => r.source !== 'marketplace')

export const exportWindowOverLimit = (total: number): boolean => total > EXPORT_MAX_ROWS

export const buildExportBlob = (rows: SpiderResult[], format: 'csv' | 'json'): Blob => {
  const isJson = format === 'json'
  return new Blob(
    [isJson ? JSON.stringify(rows, null, 2) : resultsToCsv(rows)],
    { type: isJson ? 'application/json' : 'text/csv;charset=utf-8' },
  )
}

export const triggerDownload = (blob: Blob, filename: string): void => {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}
