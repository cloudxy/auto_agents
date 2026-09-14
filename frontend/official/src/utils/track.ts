/** 官网北极星最小埋点（I3）：本地队列，不外呼。 */
const KEY = 'aa_track'

export type TrackEvent = 'view' | 'signup' | 'skill_open' | 'cta_admin'

export function track(event: TrackEvent, extra?: Record<string, string>): void {
  const row = { event, t: Date.now(), ...extra }
  try {
    const prev = JSON.parse(sessionStorage.getItem(KEY) || '[]') as unknown[]
    prev.push(row)
    sessionStorage.setItem(KEY, JSON.stringify(prev.slice(-50)))
  } catch {
    /* ignore quota */
  }
}
