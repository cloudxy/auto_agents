import { formatDate } from '@auto-agents/frontend-shared'

export interface DailyCount {
  date: string
  count: number
}

export interface TrendInput {
  daily_tasks?: DailyCount[]
  daily_results?: DailyCount[]
  /** 窗口起点（UTC，带偏移）；按北京时间切日 */
  window_start?: string | null
  window_days?: number
}

export interface TrendPoint {
  date: string
  tasks: number
  results: number
}

/**
 * 近 N 日趋势：任务数 / 结果数按日合并成一行（双折线共用 X 轴）。
 * 后端只回有数据的日子——按窗口起点补齐每一天（没跑的日子画 0，而不是在横轴上跳过）。
 */
export function buildTrendData(stats: TrendInput): TrendPoint[] {
  const map: Record<string, TrendPoint> = {}
  for (const p of stats.daily_tasks || []) map[p.date] = { date: p.date.slice(5), tasks: p.count, results: 0 }
  for (const p of stats.daily_results || []) {
    if (map[p.date]) map[p.date].results = p.count
    else map[p.date] = { date: p.date.slice(5), tasks: 0, results: p.count }
  }
  const start = formatDate(stats.window_start ?? null, '')
  if (/^\d{4}-\d{2}-\d{2}$/.test(start)) {
    const [y, m, d] = start.split('-').map(Number)
    for (let i = 0; i < (stats.window_days || 7); i += 1) {
      const day = new Date(Date.UTC(y, m - 1, d + i)).toISOString().slice(0, 10)
      if (!map[day]) map[day] = { date: day.slice(5), tasks: 0, results: 0 }
    }
  }
  return Object.keys(map).sort().map((k) => map[k])
}
