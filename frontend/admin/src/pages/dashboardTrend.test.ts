/** 近 7 日趋势补齐（批次 5）：后端只回有数据的日子，横轴不能跳天 */
import { buildTrendData } from './dashboardTrend'

test('fills every day of the window with zeros and merges both series', () => {
  const out = buildTrendData({
    // 北京 09-23 00:00 = UTC 09-22 16:00
    window_start: '2026-09-22T16:00:00+00:00',
    window_days: 7,
    daily_tasks: [{ date: '2026-09-25', count: 3 }],
    daily_results: [{ date: '2026-09-25', count: 120 }, { date: '2026-09-29', count: 8 }],
  })
  expect(out.map((p) => p.date)).toEqual(['09-23', '09-24', '09-25', '09-26', '09-27', '09-28', '09-29'])
  expect(out[2]).toEqual({ date: '09-25', tasks: 3, results: 120 })
  expect(out[6]).toEqual({ date: '09-29', tasks: 0, results: 8 })
  expect(out[0]).toEqual({ date: '09-23', tasks: 0, results: 0 })
})

test('without a window it keeps only the days the backend returned', () => {
  expect(buildTrendData({ daily_tasks: [{ date: '2026-09-25', count: 1 }] })).toEqual([
    { date: '09-25', tasks: 1, results: 0 },
  ])
})
