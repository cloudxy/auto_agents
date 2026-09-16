/**
 * T-11（FR-04 精选 / 附加 d 示例维护）+ T-15（FR-02 失源清理治理入口）：
 * 精选星标乐观更新与回滚；示例弹窗读取-保存-超限；清理失源资产二段式
 * （打开即 dry_run、确认句逐字、取消零执行、成功 toast 对账三元组）。
 */
import React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'

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
  patchFeatured: jest.fn(),
  patchExamples: jest.fn(),
  fetchPublicCapability: jest.fn(),
  pruneMissingAssets: jest.fn(),
  patchListing: jest.fn(),
}))

jest.mock('../../hooks/usePermission', () => ({
  usePermission: () => perm,
}))

import { ConfigProvider, message } from 'antd'
import CatalogTab from './CatalogTab'
import {
  EXAMPLES_LIMIT_COPY, EXAMPLES_EMPTY, EXAMPLES_LOAD_FAIL,
} from './ExamplesModal'
import {
  fetchPublicCapability, listAssets, patchExamples, patchFeatured, pruneMissingAssets,
} from '../../services/capabilities'

// CatalogTab 内嵌 AssetDetailDrawer（useQuery 读公开详情）——渲染必须带
// QueryClientProvider，否则 react-query 抛 "No QueryClient set"。retry:false
// 让失败态用例一次落地，不等指数退避。
const renderTab = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ConfigProvider button={{ autoInsertSpace: false }}>
        <CatalogTab />
      </ConfigProvider>
    </QueryClientProvider>,
  )
}

const list = listAssets as jest.Mock
const star = patchFeatured as jest.Mock
const saveExamples = patchExamples as jest.Mock
const fetchDetail = fetchPublicCapability as jest.Mock
const prune = pruneMissingAssets as jest.Mock

const row = (over: Partial<AssetRow> = {}): AssetRow => ({
  id: 1,
  asset_type: 'skill',
  name: 'demo-skill',
  title: '演示技能',
  category: 'cat',
  status: 'stable',
  sync_state: 'ok',
  listing_state: 'unlisted',
  listed_at: null,
  source_type: 'self_built',
  featured: 0,
  ...over,
})

beforeEach(() => {
  perm.isPlatformAdmin = true
  list.mockReset().mockResolvedValue({ total: 1, items: [row()] })
  star.mockReset()
  saveExamples.mockReset()
  fetchDetail.mockReset().mockResolvedValue({ name: 'demo-skill', asset_type: 'skill', examples: ['现有示例'] })
  prune.mockReset()
  ;(message.success as jest.Mock).mockClear()
  ;(message.error as jest.Mock).mockClear()
  ;(message.info as jest.Mock).mockClear()
})

test('T-11 精选星标：点击调 patchFeatured(true)，行内星标翻转', async () => {
  star.mockResolvedValue(row({ featured: 1 }))
  renderTab()
  const btn = await screen.findByRole('button', { name: '设为精选 demo-skill' })
  fireEvent.click(btn)
  await waitFor(() => expect(star).toHaveBeenCalledWith('skill', 'demo-skill', true))
  await waitFor(() => expect(screen.getByRole('button', { name: '取消精选 demo-skill' })).toBeInTheDocument())
})

test('T-11 精选失败回滚原态 + toast「操作失败：…」', async () => {
  star.mockRejectedValue({ response: { data: { message: '维护中' } } })
  renderTab()
  fireEvent.click(await screen.findByRole('button', { name: '设为精选 demo-skill' }))
  await waitFor(() => expect(message.error).toHaveBeenCalledWith('操作失败：维护中'))
  await waitFor(() => expect(screen.getByRole('button', { name: '设为精选 demo-skill' })).toBeInTheDocument())
})

test('T-11 示例弹窗：读公开详情 examples → 编辑保存调 patchExamples（trim 空行）', async () => {
  saveExamples.mockResolvedValue(row())
  renderTab()
  fireEvent.click(await screen.findByRole('button', { name: '示例' }))
  const modal = document.querySelector('.ant-modal') as HTMLElement
  expect(await within(modal).findByDisplayValue('现有示例')).toBeInTheDocument()
  // QA-3 修复回归：示例读源必须带 preview=true，否则闸关/unlisted 资产读到
  // 空列表，保存即静默覆盖已维护内容（finding QA-3 原文）
  expect(fetchDetail).toHaveBeenCalledWith('skill', 'demo-skill', true)
  fireEvent.change(within(modal).getByLabelText('示例 1'), { target: { value: '  新示例  ' } })
  fireEvent.click(within(modal).getByRole('button', { name: '保存' }))
  await waitFor(() => expect(saveExamples).toHaveBeenCalledWith('skill', 'demo-skill', ['新示例']))
  await waitFor(() => expect(message.success).toHaveBeenCalledWith('示例已保存'))
})

test('T-11 示例空态句 + 上限内联错误（超 200 字前端拦截）', async () => {
  fetchDetail.mockResolvedValue({ name: 'demo-skill', asset_type: 'skill', examples: [] })
  renderTab()
  fireEvent.click(await screen.findByRole('button', { name: '示例' }))
  const modal = document.querySelector('.ant-modal') as HTMLElement
  expect(await within(modal).findByText(EXAMPLES_EMPTY)).toBeInTheDocument()
  fireEvent.click(within(modal).getByRole('button', { name: '添加示例' }))
  fireEvent.change(within(modal).getByLabelText('示例 1'), { target: { value: 'x'.repeat(201) } })
  fireEvent.click(within(modal).getByRole('button', { name: '保存' }))
  expect(await within(modal).findByText(EXAMPLES_LIMIT_COPY)).toBeInTheDocument()
  expect(saveExamples).not.toHaveBeenCalled()
})

test('QA-3 读示例失败：锁保存按钮，不静默退化成空列表被保存覆盖', async () => {
  fetchDetail.mockRejectedValue(new Error('网络错误'))
  renderTab()
  fireEvent.click(await screen.findByRole('button', { name: '示例' }))
  const modal = document.querySelector('.ant-modal') as HTMLElement
  expect(await within(modal).findByText(EXAMPLES_LOAD_FAIL)).toBeInTheDocument()
  // 读失败时不展示「还没有示例」空态句（会被管理员误当真的没有示例）
  expect(within(modal).queryByText(EXAMPLES_EMPTY)).not.toBeInTheDocument()
  expect(within(modal).getByRole('button', { name: '保存' })).toBeDisabled()
  fireEvent.click(within(modal).getByRole('button', { name: '保存' }))
  expect(saveExamples).not.toHaveBeenCalled()
})

test('T-15 打开弹窗即发 dry_run 请求（pruneMissingAssets(true)）', async () => {
  prune.mockResolvedValue({ pruned: [], live_total: 5, disk_total: 5 })
  renderTab()
  fireEvent.click(await screen.findByRole('button', { name: '清理失源资产' }))
  await waitFor(() => expect(prune).toHaveBeenCalledWith(true))
})

test('T-15 零失源空态：「当前无失源资产」+ 确认清理禁用 + 主行动=关闭', async () => {
  prune.mockResolvedValue({ pruned: [], live_total: 5, disk_total: 5 })
  renderTab()
  fireEvent.click(await screen.findByRole('button', { name: '清理失源资产' }))
  const modal = await waitFor(() => document.querySelector('.ant-modal') as HTMLElement)
  expect(await within(modal).findByText('当前无失源资产')).toBeInTheDocument()
  expect(within(modal).getByText('存活资产与 .agents 磁盘内容一致，无需清理')).toBeInTheDocument()
  expect(within(modal).queryByRole('button', { name: '确认清理' })).not.toBeInTheDocument()
  expect(within(modal).getByRole('button', { name: '关闭' })).toBeInTheDocument()
})

test('T-15 就绪态确认句逐字「将下线 3 个无磁盘来源的资产」+ 预览清单；取消零执行 + toast', async () => {
  prune.mockResolvedValue({
    pruned: [
      { asset_type: 'command', name: 'oh-story__cover' },
      { asset_type: 'skill', name: 'orphan-skill' },
      { asset_type: 'skill', name: 'orphan-skill-2' },
    ],
    live_total: 12,
    disk_total: 9,
  })
  renderTab()
  fireEvent.click(await screen.findByRole('button', { name: '清理失源资产' }))
  const modal = await waitFor(() => document.querySelector('.ant-modal') as HTMLElement)
  expect(await within(modal).findByText('将下线 3 个无磁盘来源的资产')).toBeInTheDocument()
  expect(within(modal).getByText('oh-story__cover')).toBeInTheDocument()
  fireEvent.click(within(modal).getByRole('button', { name: '取消' }))
  // 取消零执行：不发非 dry_run 请求
  expect(prune).toHaveBeenCalledTimes(1)
  expect(prune).toHaveBeenLastCalledWith(true)
  await waitFor(() => expect(message.info).toHaveBeenCalledWith('已取消，未下线任何资产'))
})

test('T-15 确认执行不带 dry_run → toast 对账三元组 + 表格刷新', async () => {
  prune.mockResolvedValue({
    pruned: [{ asset_type: 'command', name: 'oh-story__cover' }],
    live_total: 10,
    disk_total: 9,
  })
  renderTab()
  fireEvent.click(await screen.findByRole('button', { name: '清理失源资产' }))
  const modal = await waitFor(() => document.querySelector('.ant-modal') as HTMLElement)
  fireEvent.click(await within(modal).findByRole('button', { name: '确认清理' }))
  await waitFor(() => expect(prune).toHaveBeenNthCalledWith(2, false))
  await waitFor(() => expect(message.success).toHaveBeenCalledWith(
    '清理完成：下线 1 个 · 存活 10 · 磁盘 9',
  ))
  await waitFor(() => expect(list.mock.calls.length).toBeGreaterThanOrEqual(2))
})

test('T-15 失败态：role=alert「清理失败：…请重试。」+ 重试按钮（不自动重试）', async () => {
  prune.mockRejectedValue({ response: { data: { message: 'agents 目录不可读' } } })
  renderTab()
  fireEvent.click(await screen.findByRole('button', { name: '清理失源资产' }))
  const modal = await waitFor(() => document.querySelector('.ant-modal') as HTMLElement)
  const alert = await within(modal).findByRole('alert')
  expect(alert.textContent).toContain('清理失败：agents 目录不可读。请重试。')
  expect(within(modal).getByRole('button', { name: '重试' })).toBeInTheDocument()
})

test('T-15/T-11 非超管：工具栏无清理按钮、无精选星标/示例操作', async () => {
  perm.isPlatformAdmin = false
  renderTab()
  await screen.findByText('demo-skill')
  expect(screen.queryByRole('button', { name: '清理失源资产' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '示例' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '设为精选 demo-skill' })).not.toBeInTheDocument()
})

test('T-10 治理行入口：名称单元格点开详情抽屉', async () => {
  fetchDetail.mockResolvedValue({
    name: 'demo-skill', asset_type: 'skill', title: '演示技能', gate_open: true,
    market_closed: false, skill_md: '# 演示', listing_state: 'unlisted', preview: true,
  })
  renderTab()
  fireEvent.click(await screen.findByRole('button', { name: '查看 演示技能 详情' }))
  // QA-2 修复回归：治理面开抽屉必须恒 preview=true（否则 unlisted 资产 404，
  // 刚导入的资产在治理面永远看不到详情——finding QA-2 后果链原文）
  await waitFor(() => expect(fetchDetail).toHaveBeenCalledWith('skill', 'demo-skill', true))
  await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument())
})
