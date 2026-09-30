/**
 * 跨应用共享 HTTP client 工厂（D3：工厂非单例）
 *
 * 两应用鉴权语义不同：admin 注入 zustand token + 401 导航；
 * official 无鉴权只传 baseURL。单例会把 admin 逻辑漏进官网，故必须工厂化。
 */
import axios, { AxiosInstance, InternalAxiosRequestConfig } from 'axios'

export interface ApiClientOptions {
  /** API 基地址（如 http://localhost:9111/api/v1） */
  baseURL: string
  /** 请求超时（毫秒），默认 10000 */
  timeout?: number
  /** 鉴权 token 读取器（admin：zustand store getter；official 不传） */
  getAuthToken?: () => string | null | undefined
  /** 401 回调（admin：清登录态 + navigate('/login', {state:{from}})；official 不传） */
  onUnauthorized?: () => void
  /**
   * 静默续期（决策 D10）：访问令牌过期（401）时调用一次，成功返回 true 后用新令牌重放原请求；
   * 返回 false / 抛错则走 onUnauthorized。并发的多个 401 共用同一次续期。
   */
  refreshSession?: () => Promise<boolean>
}

/** 自身的 401 不再触发续期（登录失败、续期失败、登出） */
const NO_REFRESH_PATHS = ['/auth/login', '/auth/refresh', '/auth/logout']

type RetriableConfig = InternalAxiosRequestConfig & { _sessionRetried?: boolean }

/**
 * 创建 API client：响应拦截器剥掉 axios 层（直接返回信封体），
 * 请求拦截器按需注入 Bearer token。
 */
export function createApiClient(options: ApiClientOptions): AxiosInstance {
  // 不设实例级 Content-Type（审计 R5-1 / BUG-07）：axios 1.x 见到显式 application/json
  // 会把 FormData 转成 JSON 字符串，上传接口收不到文件。交给 axios 按请求体推断：
  // 普通对象 → application/json；FormData → 浏览器自带 multipart boundary。
  const client = axios.create({
    baseURL: options.baseURL,
    timeout: options.timeout ?? 10000,
  })

  const getAuthToken = options.getAuthToken
  if (getAuthToken) {
    client.interceptors.request.use(
      (config) => {
        const token = getAuthToken()
        if (token) {
          config.headers.Authorization = `Bearer ${token}`
        }
        return config
      },
      (error) => Promise.reject(error),
    )
  }

  let refreshing: Promise<boolean> | null = null
  const refreshOnce = (): Promise<boolean> => {
    if (!options.refreshSession) return Promise.resolve(false)
    if (!refreshing) {
      refreshing = options.refreshSession()
        .catch(() => false)
        .finally(() => { refreshing = null })
    }
    return refreshing
  }

  client.interceptors.response.use(
    (response) => response.data,
    async (error) => {
      const config = error.config as RetriableConfig | undefined
      if (error.response?.status !== 401) return Promise.reject(error)
      const url = String(config?.url ?? '')
      const refreshable = Boolean(options.refreshSession) && config && !config._sessionRetried
        && !NO_REFRESH_PATHS.some((p) => url.includes(p))
      if (refreshable && (await refreshOnce())) {
        config._sessionRetried = true
        return client.request(config)
      }
      options.onUnauthorized?.()
      return Promise.reject(error)
    },
  )

  return client
}
