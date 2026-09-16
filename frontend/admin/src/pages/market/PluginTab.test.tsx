/**
 * T-02（FR-01 / GWT-01.6 治理面入口）：PluginTab「同步 .agents」四态——
 * 成功 toast 对账三元组 + 列表刷新；失败 toast 带非破坏承诺句；旧扫描入口不存在。
 */
import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import type { AssetRow } from '../../services/capabilities'

jest.mock('antd', () => {
  const actual = jest.requireActual('antd')
  return {
    ...actual,
    message: { error: jest.fn(), success: jest.fn(), warning: jest.fn(), info: jest.fn() },
  }
})

const perm = { isPlatformAdmin: true }

jest.mock('../../services/capabilities', () => ({
  listAssets: jest.fn(),
  getPlugin: jest.fn(),
  patchListing: jest.fn(),
  verifyPlugin: jest.fn(),
  syncAgentsHub: jest.fn(),
}))

jest.mock('../../hooks/usePermission', () => ({
  usePermission: () => perm,
}))

import { message } from 'antd'
import PluginTab from './PluginTab'
import { listAssets, syncAgentsHub } from '../../services/capabilities'
import { SYNCING, SYNC_AGENTS, syncDoneCopy, syncFailCopy } from './marketCopy'

const list = listAssets as jest.Mock
const sync = syncAgentsHub as jest.Mock

const row = (over: Partial<AssetRow> = {}): AssetRow => ({
  id: 1,
  asset_type: 'plugin',
  name: 'dev-team',
  title: 'dev-team',
  category: 'cat',
  status: 'stable',
  sync_state: 'ok',
  listing_state: 'unlisted',
  listed_at: null,
  source_type: 'self_built',
  ...over,
})

const noop = () => undefined

beforeEach(() => {
  perm.isPlatformAdmin = true
  list.mockReset().mockResolvedValue({ total: 1, items: [row()] })
  sync.mockReset()
  ;(message.success as jest.Mock).mockClear()
  ;(message.error as jest.Mock).mockClear()
})

test('GWT-01.6 同步 .agents 成功：toast 对账三元组 + 列表刷新，旧「扫描插件目录」入口不存在', async () => {
  sync.mockResolvedValue({ inserted: 2, updated: 1, unchanged: 3, failed: 0, total: 6 })
  render(<PluginTab onSubscribe={noop} onOpenCatalog={noop} />)
  expect((await screen.findAllByText('dev-team')).length).toBeGreaterThan(0)
  const callsBefore = list.mock.calls.length
  expect(screen.queryByRole('button', { name: '扫描插件目录' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: SYNC_AGENTS }))
  await waitFor(() => expect(sync).toHaveBeenCalledTimes(1))
  await waitFor(() => expect(list.mock.calls.length).toBeGreaterThan(callsBefore))
  await waitFor(() => expect(message.success).toHaveBeenCalledWith(
    syncDoneCopy(2, 1, 3),
  ))
  expect(message.success).toHaveBeenCalledWith('同步完成：新增 2 · 更新 1 · 无变化 3')
})

test('同步失败：toast 带非破坏承诺句「已有数据未受影响」，列表保持旧行', async () => {
  sync.mockRejectedValue({ response: { data: { message: 'agents 目录不可读' } } })
  render(<PluginTab onSubscribe={noop} onOpenCatalog={noop} />)
  expect((await screen.findAllByText('dev-team')).length).toBeGreaterThan(0)
  fireEvent.click(screen.getByRole('button', { name: SYNC_AGENTS }))
  await waitFor(() => expect(message.error).toHaveBeenCalledWith(
    syncFailCopy('agents 目录不可读'),
  ))
  expect(message.error).toHaveBeenCalledWith('同步失败：agents 目录不可读。已有数据未受影响。')
  // 非破坏语义：失败后不刷新、旧行仍在
  expect((await screen.findAllByText('dev-team')).length).toBeGreaterThan(0)
})

test('同步中按钮 loading 且防重复触发（同步中…文案）', async () => {
  let release: () => void = () => undefined
  sync.mockImplementation(() => new Promise((resolve) => {
    release = () => resolve({ inserted: 0, updated: 0, unchanged: 1, failed: 0, total: 1 })
  }))
  render(<PluginTab onSubscribe={noop} onOpenCatalog={noop} />)
  fireEvent.click(await screen.findByRole('button', { name: SYNC_AGENTS }))
  // antd v6 loading 不落 disabled 属性：以 ant-btn-loading 类 + syncing 守卫防重复触发（仓库既有约定）；
  // loading 图标带 aria-label=loading，按子串匹配按钮名
  const busy = await screen.findByRole('button', { name: /同步中…/ })
  expect(busy.className).toMatch(/ant-btn-loading/)
  fireEvent.click(busy)
  expect(sync).toHaveBeenCalledTimes(1)
  release()
  await waitFor(() => expect(message.success).toHaveBeenCalled())
})

test('非超管不渲染同步入口（越权 404 门面由后端兜底，前端无入口）', async () => {
  perm.isPlatformAdmin = false
  render(<PluginTab onSubscribe={noop} onOpenCatalog={noop} />)
  expect((await screen.findAllByText('dev-team')).length).toBeGreaterThan(0)
  expect(screen.queryByRole('button', { name: SYNC_AGENTS })).not.toBeInTheDocument()
})
