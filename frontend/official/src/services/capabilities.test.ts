/**
 * T-14（GWT-92.5 前端半）：翻页请求（page ≥ 2）携带浏览会话 anonymous_id；
 * 后端在该请求上上报 market_list_paged（访客无 tenant_id）。
 */
jest.mock('./api', () => ({
  __esModule: true,
  default: { get: jest.fn().mockResolvedValue({ data: { data: { items: [], total: 0 } } }) },
  unwrap: (r: { data: { data: unknown } }) => r.data.data,
}))

import api from './api'
import { listPublicAssets } from './capabilities'

const get = api.get as jest.MockedFunction<typeof api.get>

beforeEach(() => {
  get.mockClear()
  window.localStorage.setItem('aa_anonymous_id', 'anon-t14-service')
})

test('page 2 list request carries anonymous_id (GWT-92.5)', async () => {
  await listPublicAssets({ page: 2, page_size: 20 })
  expect(get).toHaveBeenCalledWith('/public/capabilities', {
    params: expect.objectContaining({
      page: 2,
      page_size: 20,
      anonymous_id: 'anon-t14-service',
    }),
  })
})

test('page 1 list request does not carry anonymous_id', async () => {
  await listPublicAssets({ page: 1, page_size: 20 })
  const params = get.mock.calls[0][1]?.params as Record<string, unknown> | undefined
  expect(params).toEqual(expect.objectContaining({ page: 1 }))
  expect(params).not.toHaveProperty('anonymous_id')
})
