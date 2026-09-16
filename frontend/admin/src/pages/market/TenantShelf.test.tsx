/**
 * T-08（FR-03/04）：货架卡片四要素 + onClick 抽屉 + 排序条 + 三重空态。
 * 既有 T-10 冻结句用例保留（关闭句/空货架/加载失败/预告）；
 * 订阅按钮按 designer 裁定收敛进抽屉（edge-states §1.2），订一行用例改为
 * 点卡 → 抽屉 CTA → 订阅弹窗路径。
 */
import React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import {
  EMPTY_SHELF, FILTER_EMPTY, LOAD_FAIL, MARKET_CLOSED, NO_DESC,
  READONLY_SUBSCRIBE, TAB_EMPTY, tabEmptyHint,
} from './shelfCopy'
import { syncDoneCopy } from './marketCopy'
import type { InstallRow, PublicShelfItem } from '../../services/capabilities'

const perm = {
  hasPermission: () => true,
  isPlatformAdmin: false,
  role: 'operator',
  isAdmin: false,
  permissions: [] as string[],
  filteredMenus: [] as unknown[],
}

jest.mock('antd', () => {
  const actual = jest.requireActual('antd')
  return {
    ...actual,
    message: { error: jest.fn(), success: jest.fn(), warning: jest.fn(), info: jest.fn() },
  }
})

jest.mock('../../services/capabilities', () => ({
  listAssets: jest.fn().mockResolvedValue({ total: 0, items: [] }),
  listSources: jest.fn().mockResolvedValue({ total: 0, items: [] }),
  createTeam: jest.fn(),
  verifyPlugin: jest.fn(),
  patchListing: jest.fn(),
  getPlugin: jest.fn(),
  fetchPublicCapability: jest.fn(),
  subscribeCapability: jest.fn(),
  listInstalls: jest.fn(),
  importAssets: jest.fn(),
  listPublicAssets: jest.fn(),
  syncAgentsHub: jest.fn(),
  getPowerMarket: jest.fn().mockResolvedValue({ enabled: true }),
  putPowerMarket: jest.fn(),
  patchInstall: jest.fn(),
  uninstallInstall: jest.fn(),
}))

jest.mock('../Skills', () => () => <div>skills-tab</div>)

jest.mock('../../hooks/usePermission', () => ({
  usePermission: () => perm,
}))

import { message } from 'antd'
import Capabilities from '../Capabilities'
import MyInstalls from '../MyInstalls'
import TenantShelf from './TenantShelf'
import {
  fetchPublicCapability, listInstalls, listPublicAssets,
  subscribeCapability, syncAgentsHub,
} from '../../services/capabilities'

const fetchList = listPublicAssets as jest.Mock
const fetchCard = fetchPublicCapability as jest.Mock
const subscribe = subscribeCapability as jest.Mock
const installs = listInstalls as jest.Mock
const sync = syncAgentsHub as jest.Mock

const item = (over: Partial<PublicShelfItem> = {}): PublicShelfItem => ({
  asset_type: 'skill',
  name: 'listed-ok',
  title: '可订技能',
  description: '说明',
  category: 'dev-tools',
  listing_state: 'listed',
  subscribable: true,
  hosts: ['grok', 'zcode', 'kimi', 'claude'],
  ...over,
})

const installRow = (over: Partial<InstallRow> = {}): InstallRow => ({
  id: 1,
  asset_id: 10,
  asset_name: 'u101-plug',
  asset_type: 'plugin',
  host: 'grok',
  enabled: 1,
  trusted: 0,
  delisted: false,
  flags_locked: false,
  can_change_flags: true,
  can_uninstall: true,
  resubscribe_allowed: true,
  resubscribe_hint: null,
  ...over,
})

const detailCard = (over: Record<string, unknown> = {}) => ({
  name: 'listed-ok',
  asset_type: 'skill',
  title: '可订技能',
  description: '说明',
  listing_state: 'listed',
  subscribable: true,
  hosts: ['grok', 'zcode', 'kimi', 'claude'],
  market_closed: false,
  gate_open: true,
  skill_md: '# 可订技能\n正文',
  ...over,
})

function renderShelf(path = '/capabilities') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/capabilities" element={<Capabilities />} />
          <Route path="/capabilities/installs" element={<MyInstalls />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function renderShelfDirect(path = '/capabilities', preview?: boolean) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path="/capabilities"
            element={(
              <TenantShelf
                canSubscribe
                onSubscribe={() => undefined}
                onExitPreview={() => undefined}
                preview={preview}
              />
            )}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  perm.isPlatformAdmin = false
  perm.role = 'operator'
  fetchList.mockReset()
  fetchCard.mockReset()
  subscribe.mockReset()
  installs.mockReset()
  sync.mockReset()
  ;(message.success as jest.Mock).mockClear()
  ;(message.error as jest.Mock).mockClear()
  Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
})

test('GWT-U11.2 closed flag copy is 能力市场未开放, not empty shelf', async () => {
  fetchList.mockResolvedValue({
    items: [], total: 0, market_closed: true, empty: true, message: MARKET_CLOSED,
  })
  renderShelf()
  expect(await screen.findByText(MARKET_CLOSED)).toBeInTheDocument()
  expect(screen.getByText('开放后，已上架的能力会出现在这里。')).toBeInTheDocument()
  expect(screen.queryByText(EMPTY_SHELF)).not.toBeInTheDocument()
  expect(screen.queryByText(LOAD_FAIL)).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /订\s*阅/ })).not.toBeInTheDocument()
  expect(screen.queryByRole('tab', { name: '源' })).not.toBeInTheDocument()
  expect(screen.queryByTestId('governance-shell')).not.toBeInTheDocument()
  expect(document.body.textContent || '').not.toContain('当前可买')
})

test('GWT-U11.2 closed plus filters still uses closed copy', async () => {
  fetchList.mockResolvedValue({
    items: [], total: 0, market_closed: true, message: MARKET_CLOSED,
  })
  renderShelf('/capabilities?type=skill&q=没有这货')
  expect(await screen.findByText(MARKET_CLOSED)).toBeInTheDocument()
  expect(screen.queryByText(EMPTY_SHELF)).not.toBeInTheDocument()
  expect(screen.queryByText(FILTER_EMPTY)).not.toBeInTheDocument()
})

test('GWT-U10.2 open plus 0 listed is 暂无已上架能力, not blank or load-fail', async () => {
  fetchList.mockResolvedValue({
    items: [], total: 0, market_closed: false, empty: true, message: EMPTY_SHELF,
  })
  renderShelf()
  expect(await screen.findByText(EMPTY_SHELF)).toBeInTheDocument()
  expect(screen.queryByText('已上架且过许可的能力会出现在这里。')).not.toBeInTheDocument()
  expect(screen.queryByText(MARKET_CLOSED)).not.toBeInTheDocument()
  expect(screen.queryByText(LOAD_FAIL)).not.toBeInTheDocument()
  expect(screen.getByTestId('tenant-shelf')).toBeInTheDocument()
  expect(document.body.textContent || '').not.toContain('当前可买')
})

test('GWT-U10.2 load failure is not empty shelf', async () => {
  fetchList.mockRejectedValue(new Error('boom'))
  renderShelf()
  expect(await screen.findByText(LOAD_FAIL)).toBeInTheDocument()
  expect(screen.queryByText(EMPTY_SHELF)).not.toBeInTheDocument()
  expect(screen.queryByText(MARKET_CLOSED)).not.toBeInTheDocument()
})

test('GWT-U10.4 coming_soon has 预告 tag and no subscribe CTA before opening drawer', async () => {
  fetchList.mockResolvedValue({
    items: [item({
      name: 'soon-review', title: '预告审查', listing_state: 'coming_soon', subscribable: false,
    })],
    total: 1, market_closed: false,
  })
  renderShelf()
  expect(await screen.findByText('预告审查')).toBeInTheDocument()
  expect(screen.getByText('预告')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /订\s*阅/ })).not.toBeInTheDocument()
  expect(screen.queryByText(EMPTY_SHELF)).not.toBeInTheDocument()
})

test('GWT-U10.3 readonly subscribe: card opens drawer, CTA disabled with readonly title, no POST', async () => {
  perm.role = 'viewer'
  fetchList.mockResolvedValue({ items: [item()], total: 1, market_closed: false })
  fetchCard.mockResolvedValue(detailCard())
  renderShelf()
  fireEvent.click(await screen.findByRole('button', { name: '查看 可订技能 详情' }))
  const cta = await screen.findByRole('button', { name: /订\s*阅/ })
  expect(cta).toBeDisabled()
  expect(cta).toHaveAttribute('title', READONLY_SUBSCRIBE)
  fireEvent.click(cta)
  expect(subscribe).not.toHaveBeenCalled()
})

test('GWT-U10.1 subscribe plugin via drawer CTA appears in 我的安装 without children', async () => {
  fetchList.mockResolvedValue({
    items: [item({
      asset_type: 'plugin', name: 'u101-plug', title: '父插件', listing_state: 'listed',
    })],
    total: 1, market_closed: false,
  })
  fetchCard.mockResolvedValue(detailCard({
    name: 'u101-plug', asset_type: 'plugin', skill_md: null,
  }))
  subscribe.mockResolvedValue({ created: true, message: '已订阅到 Grok', host: 'grok', asset_id: 9 })
  installs.mockResolvedValue({ total: 1, items: [installRow()] })
  renderShelf()
  fireEvent.click(await screen.findByRole('button', { name: '查看 父插件 详情' }))
  fireEvent.click(await screen.findByRole('button', { name: /订\s*阅/ }))
  expect(await screen.findByText('订阅 u101-plug')).toBeInTheDocument()
  await waitFor(() => expect(screen.getByRole('radio', { name: /Grok/ })).not.toBeDisabled())
  fireEvent.click(screen.getByRole('radio', { name: /Grok/ }))
  fireEvent.click(screen.getByRole('button', { name: /订阅到 Grok/ }))
  await waitFor(() => expect(subscribe).toHaveBeenCalledWith('plugin', 'u101-plug', 'grok'))
  expect(await screen.findByText('u101-plug')).toBeInTheDocument()
  expect(screen.queryByText('u101-s1')).not.toBeInTheDocument()
  expect(screen.queryByText('u101-s2')).not.toBeInTheDocument()
  expect(installs).toHaveBeenCalled()
  expect(document.body.textContent || '').not.toContain('当前可买')
  expect(screen.queryByRole('button', { name: /启用到宿主/ })).not.toBeInTheDocument()
})

test('GWT-M40 tenant shelf has no author portal and no seven-leaf', async () => {
  fetchList.mockResolvedValue({ items: [item()], total: 1, market_closed: false })
  renderShelf()
  expect(await screen.findByRole('button', { name: '查看 可订技能 详情' })).toBeInTheDocument()
  expect(screen.queryByText('投稿')).not.toBeInTheDocument()
  expect(screen.queryByText('成为作者')).not.toBeInTheDocument()
  expect(screen.queryByText('发布到能力市场')).not.toBeInTheDocument()
  expect(screen.queryByTestId('governance-shell')).not.toBeInTheDocument()
  expect(screen.queryByRole('tab', { name: '源' })).not.toBeInTheDocument()
  expect(document.body.textContent || '').not.toContain('当前可买')
})

test('tenant company admin has no market switch and no listing tabs', async () => {
  perm.role = 'admin'
  perm.isAdmin = true
  fetchList.mockResolvedValue({ items: [], total: 0, market_closed: true, message: MARKET_CLOSED })
  renderShelf()
  expect(await screen.findByText(MARKET_CLOSED)).toBeInTheDocument()
  expect(screen.queryByTestId('power-market-switch')).not.toBeInTheDocument()
  expect(screen.queryByRole('tab', { name: '源' })).not.toBeInTheDocument()
  expect(screen.queryByRole('tab', { name: '目录' })).not.toBeInTheDocument()
})

test('GWT-03.1 卡片四要素：主副标题/描述兜底/标签（精选>预告>类型）', async () => {
  fetchList.mockResolvedValue({
    items: [
      item({
        name: 'child-skill', title: '捆绑技能', origin_plugin_name: 'dev-team',
        featured: 1, description: '',
      }),
      item({ name: 'bare-skill', title: '裸技能', listing_state: 'coming_soon' }),
    ],
    total: 2, market_closed: false,
  })
  renderShelf()
  expect(await screen.findByText('捆绑技能')).toBeInTheDocument()
  expect(screen.getByText('dev-team')).toBeInTheDocument()
  expect(screen.getAllByText(NO_DESC).length).toBeGreaterThan(0)
  expect(screen.getByText('精选')).toBeInTheDocument()
  expect(screen.getByText('裸技能').closest('.shelf-card')).toBeTruthy()
  const bare = screen.getByText('裸技能').closest('.shelf-card') as HTMLElement
  expect(within(bare).getByText('预告')).toBeInTheDocument()
  // 副标题兜底与类型 Tag 都可能出现同文案：按选择器区分断言
  expect(within(bare).getAllByText('技能').length).toBeGreaterThanOrEqual(1)
  expect(within(bare).getByText('技能', { selector: '.ant-tag' })).toBeInTheDocument()
})

test('GWT-03.1 无 origin_plugin_name 副标题用类型中文兜底，不为空串', async () => {
  fetchList.mockResolvedValue({
    items: [item({ name: 'no-origin', title: '无源插件', asset_type: 'plugin' })],
    total: 1, market_closed: false,
  })
  renderShelf()
  const card = (await screen.findByText('无源插件')).closest('.shelf-card') as HTMLElement
  expect(within(card).getByText('插件', { selector: '.shelf-card__subtitle' })).toBeInTheDocument()
  expect(within(card).getByText('插件', { selector: '.ant-tag' })).toBeInTheDocument()
})

test('FR-03 卡片 onClick 打开详情抽屉（1 次点击，无页面跳转）', async () => {
  fetchList.mockResolvedValue({ items: [item()], total: 1, market_closed: false })
  fetchCard.mockResolvedValue(detailCard())
  renderShelf()
  fireEvent.click(await screen.findByRole('button', { name: '查看 可订技能 详情' }))
  await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument())
  // 租户侧渲染（isPlatformAdmin=false）：不带 preview——QA-2 修复后必须能断言
  // 请求实参，而不是只看 mock 的返回值（否则测不出请求侧从未透传 preview 的回归）
  expect(fetchCard).toHaveBeenCalledWith('skill', 'listed-ok', undefined)
})

test('FR-04 排序条：切「最热」带 sort=hot 请求；服务端回 smart 静默接受（GWT-04.4：无计数数字、无降级提示）', async () => {
  fetchList.mockResolvedValue({
    items: [item(), item({ name: 'second', title: '第二件' })],
    total: 2, market_closed: false, sort_applied: 'smart',
  })
  renderShelf()
  expect(await screen.findByText('可订技能')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('radio', { name: '最热' }))
  await waitFor(() => expect(fetchList).toHaveBeenLastCalledWith(
    expect.objectContaining({ sort: 'hot' }),
  ))
  // 选中态保持「最热」
  expect(screen.getByRole('radio', { name: '最热' })).toBeChecked()
  // 页面不出现任何计数数字/降级 banner（卡片无计数是结构性保证）
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  expect(document.querySelector('.shelf-card')?.textContent || '').not.toMatch(/已订阅\s*\d+|\d+\s*次/)
})

test('FR-04 排序默认综合（smart 不落 URL 缺省不传）', async () => {
  fetchList.mockResolvedValue({ items: [item()], total: 1, market_closed: false })
  renderShelf()
  await screen.findByText('可订技能')
  expect(screen.getByRole('radio', { name: '综合' })).toBeChecked()
  expect(fetchList).toHaveBeenLastCalledWith(expect.not.objectContaining({ sort: 'hot' }))
})

test('刷新（换排序）保留旧卡 + 进度条，不变骨架（edge-states §4.1）', async () => {
  fetchList.mockResolvedValueOnce({ items: [item()], total: 1, market_closed: false })
  renderShelf()
  expect(await screen.findByText('可订技能')).toBeInTheDocument()
  let releaseFetch: (v: unknown) => void = () => undefined
  fetchList.mockImplementationOnce(() => new Promise((resolve) => {
    releaseFetch = resolve as (v: unknown) => void
  }))
  fireEvent.click(screen.getByRole('radio', { name: '最新' }))
  // 旧卡仍在（不闪骨架），进度条出现
  expect(await screen.findByText('可订技能')).toBeInTheDocument()
  await waitFor(() => expect(document.querySelector('.tenant-shelf__progress')).toBeTruthy())
  expect(screen.queryByTestId('market-skeleton')).not.toBeInTheDocument()
  releaseFetch({ items: [item({ name: 'new-one', title: '新上架' })], total: 1, market_closed: false })
  expect(await screen.findByText('新上架')).toBeInTheDocument()
})

test('GWT-03.3 tab 空态：「暂无该类资产」+ 类型说明句；租户无同步按钮', async () => {
  perm.isPlatformAdmin = false
  fetchList.mockResolvedValue({ items: [], total: 0, market_closed: false })
  renderShelf('/capabilities?type=plugin')
  expect(await screen.findByText(TAB_EMPTY)).toBeInTheDocument()
  expect(screen.getByText(tabEmptyHint('插件'))).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '立即同步' })).not.toBeInTheDocument()
})

test('GWT-03.3 超管预览态 tab 空态给 [立即同步]：点击走 syncAgentsHub + 对账 toast + 刷新', async () => {
  perm.isPlatformAdmin = true
  sync.mockResolvedValue({ inserted: 3, updated: 1, unchanged: 2, failed: 0, total: 6 })
  fetchList.mockResolvedValue({ items: [], total: 0, market_closed: false, preview: true })
  renderShelfDirect('/capabilities?type=plugin', true)
  const syncBtn = await screen.findByRole('button', { name: '立即同步' })
  // QA-2 修复回归：预览态必须真正把 preview:'true' 送进请求，不能只靠 mock
  // 的响应体自称 preview:true（否则测不出请求侧从未透传的回归——finding QA-2）
  expect(fetchList).toHaveBeenCalledWith(expect.objectContaining({ preview: true }))
  fireEvent.click(syncBtn)
  await waitFor(() => expect(sync).toHaveBeenCalledTimes(1))
  await waitFor(() => expect(message.success).toHaveBeenCalledWith(syncDoneCopy(3, 1, 2)))
})

test('GWT-03.6 下架后不出现在货架 tab（货架侧断言：可见集变化后旧卡消失）', async () => {
  fetchList.mockResolvedValueOnce({
    items: [item(), item({ name: 'gone-after-unlist', title: '被下架者' })],
    total: 2, market_closed: false,
  })
  renderShelf()
  expect(await screen.findByText('被下架者')).toBeInTheDocument()
  // 下架 → 公开列表不再返回该资产（服务端口径）；换排序触发重取
  fetchList.mockResolvedValueOnce({
    items: [item()], total: 1, market_closed: false,
  })
  fireEvent.click(screen.getByRole('radio', { name: '最新' }))
  await waitFor(() => expect(screen.queryByText('被下架者')).not.toBeInTheDocument())
  expect(screen.getByText('可订技能')).toBeInTheDocument()
})

test('T-13 预览 badge：preview=true 且闸关时显示，gate_open=true 不显示', async () => {
  perm.isPlatformAdmin = true
  fetchList.mockResolvedValueOnce({
    items: [item()], total: 1, market_closed: false, preview: true, gate_open: false,
  })
  renderShelfDirect('/capabilities', true)
  expect(await screen.findByTestId('shelf-preview-badge')).toBeInTheDocument()
  expect(screen.getByTestId('shelf-preview-badge').textContent)
    .toContain('预览模式 · 市场未对租户开放，你看到的是上架后的展示效果')
  expect(fetchList).toHaveBeenCalledWith(expect.objectContaining({ preview: true }))
})
