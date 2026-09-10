/**
 * 跨应用共享 HTTP client 工厂（D3：工厂非单例）
 *
 * 两应用鉴权语义不同：admin 注入 zustand token + 401 导航；
 * official 无鉴权只传 baseURL。单例会把 admin 逻辑漏进官网，故必须工厂化。
 */
import axios, { AxiosInstance } from 'axios'

export interface ApiClientOptions {
  /** API 基地址（如 http://localhost:9111/api/v1） */
  baseURL: string
  /** 请求超时（毫秒），默认 10000 */
  timeout?: number
  /** 鉴权 token 读取器（admin：zustand store getter；official 不传） */
  getAuthToken?: () => string | null | undefined
  /** 401 回调（admin：清登录态 + navigate('/login', {state:{from}})；official 不传） */
  onUnauthorized?: () => void
}

/**
 * 创建 API client：响应拦截器剥掉 axios 层（直接返回信封体），
 * 请求拦截器按需注入 Bearer token。
 */
export function createApiClient(options: ApiClientOptions): AxiosInstance {
  const client = axios.create({
    baseURL: options.baseURL,
    timeout: options.timeout ?? 10000,
    headers: {
      'Content-Type': 'application/json',
    },
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

  client.interceptors.response.use(
    (response) => response.data,
    (error) => {
      if (error.response?.status === 401) {
        options.onUnauthorized?.()
      }
      return Promise.reject(error)
    },
  )

  return client
}
