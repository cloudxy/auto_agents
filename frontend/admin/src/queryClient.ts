import { QueryClient } from '@tanstack/react-query'

/**
 * react-query 全局客户端（工单 78：轮询/缓存/失焦暂停统一托管）。
 * 单独成模块：登出时要清空缓存（上一个账号的数据不能残留给下一个账号）。
 */
export const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})
