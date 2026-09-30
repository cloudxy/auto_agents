/**
 * 共享 HTTP client 契约（审计 R5-1 / BUG-07 回归）
 *
 * 直接测编译产物（@auto-agents/frontend-shared → dist），与线上消费同一份代码：
 * - FormData 请求体原样交给适配器，Content-Type 不得是 application/json
 * - 普通对象请求体序列化为 JSON，Content-Type 为 application/json
 */
import type { InternalAxiosRequestConfig } from 'axios'
import { createApiClient } from '@auto-agents/frontend-shared'

function captureClient() {
  const seen: InternalAxiosRequestConfig[] = []
  const client = createApiClient({ baseURL: 'http://api.test/api/v1' })
  client.defaults.adapter = async (config) => {
    seen.push(config)
    return { data: { success: true, data: null }, status: 200, statusText: 'OK', headers: {}, config }
  }
  return { client, seen }
}

function contentType(config: InternalAxiosRequestConfig): string {
  const raw = config.headers?.get?.('Content-Type') ?? config.headers?.['Content-Type']
  return String(raw ?? '')
}

test('FormData 上传保持 multipart，不被转成 JSON', async () => {
  const { client, seen } = captureClient()
  const form = new FormData()
  form.append('file', new Blob(['hello'], { type: 'text/plain' }), 'a.txt')
  await client.post('/capabilities/import', form)
  expect(seen).toHaveLength(1)
  expect(seen[0].data).toBeInstanceOf(FormData)
  expect(contentType(seen[0])).not.toContain('application/json')
})

test('普通对象请求体仍以 JSON 发送', async () => {
  const { client, seen } = captureClient()
  await client.post('/members', { username: 'a' })
  expect(typeof seen[0].data).toBe('string')
  expect(JSON.parse(seen[0].data as string)).toEqual({ username: 'a' })
  expect(contentType(seen[0])).toContain('application/json')
})

// ---- 决策 D10：访问令牌过期 → 静默续期一次后重放原请求 ----

function refreshingClient(opts: { refreshOk: boolean }) {
  let token = 'old'
  const calls: string[] = []
  let refreshCount = 0
  const unauthorized = jest.fn()
  const client = createApiClient({
    baseURL: 'http://api.test/api/v1',
    getAuthToken: () => token,
    onUnauthorized: unauthorized,
    refreshSession: async () => {
      refreshCount += 1
      await new Promise((r) => setTimeout(r, 10))
      if (opts.refreshOk) token = 'new'
      return opts.refreshOk
    },
  })
  client.defaults.adapter = async (config) => {
    const auth = String(config.headers?.Authorization ?? '')
    calls.push(`${config.url} ${auth}`)
    if (auth !== 'Bearer new') {
      const err = Object.assign(new Error('401'), {
        isAxiosError: true, config,
        response: { status: 401, data: { code: 'AUTH_FAILED' }, statusText: 'Unauthorized', headers: {}, config },
      })
      throw err
    }
    return { data: { success: true, data: config.url }, status: 200, statusText: 'OK', headers: {}, config }
  }
  return { client, calls, unauthorized, refreshes: () => refreshCount }
}

test('401 → 刷新一次后用新令牌重放；并发的多个 401 只刷新一次', async () => {
  const { client, unauthorized, refreshes } = refreshingClient({ refreshOk: true })
  const [a, b] = await Promise.all([client.get('/a'), client.get('/b')])
  expect((a as unknown as { data: string }).data).toBe('/a')
  expect((b as unknown as { data: string }).data).toBe('/b')
  expect(refreshes()).toBe(1)
  expect(unauthorized).not.toHaveBeenCalled()
})

test('刷新失败 → 走登出回调，原请求报错', async () => {
  const { client, unauthorized, refreshes } = refreshingClient({ refreshOk: false })
  await expect(client.get('/a')).rejects.toBeTruthy()
  expect(refreshes()).toBe(1)
  expect(unauthorized).toHaveBeenCalledTimes(1)
})

test('登录 / 刷新接口自己的 401 不再触发刷新', async () => {
  const { client, unauthorized, refreshes } = refreshingClient({ refreshOk: true })
  await expect(client.post('/auth/login', {})).rejects.toBeTruthy()
  expect(refreshes()).toBe(0)
  expect(unauthorized).toHaveBeenCalledTimes(1)
})
