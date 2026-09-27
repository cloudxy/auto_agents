/**
 * 请求三态（F1）：loading / error / empty / ready
 * 无 UI 依赖（shared 禁止 antd）；admin/official 各自接骨架与 Alert。
 */
export type QueryViewState = 'loading' | 'error' | 'empty' | 'ready'

export function queryViewState(input: {
  loading: boolean
  error?: string | null
  data: unknown
  isEmpty?: boolean
}): QueryViewState {
  if (input.loading) return 'loading'
  if (input.error) return 'error'
  if (input.isEmpty === true || input.data == null) return 'empty'
  return 'ready'
}
