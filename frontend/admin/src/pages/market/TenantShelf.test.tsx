/**
 * T-10 FR-U10/U11：租户货架关闭句 vs 空货架；订一行进我的安装；预告无订阅。
 */
import React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import {
  EMPTY_SHELF, FILTER_EMPTY, LOAD_FAIL,
  MARKET_CLOSED, READONLY_SUBSCRIBE,
} from './shelfCopy'
import type { InstallRow, PublicShelfItem } from '../../services/capabilities'

const perm = {
  hasPermission: () => true,
  isPlatformAdmin: false,
  role: 'operator',
  isAdmin: false,
  permissions: [] as string[],
  filteredMenus: [] as unknown[],
}

jest.mock('../../services/capabilities', () => ({
  listAssets: jest.fn().mockResolvedValue({ total: 0, items: [] }),
  listSources: jest.fn().mockResolvedValue({ total: 0, items: [] }),
  scanPlugins: jest.fn(),
  scanExperts: jest.fn(),
  createTeam: jest.fn(),
  verifyPlugin: jest.fn(),
  patchListing: jest.fn(),
  getPlugin: jest.fn(),
  fetchPublicCapability: jest.fn(),
  subscribeCapability: jest.fn(),
  listInstalls: jest.fn(),
  importAssets: jest.fn(),
  listPublicAssets: jest.fn(),
  getPowerMarket: jest.fn().mockResolvedValue({ enabled: true }),
  putPowerMarket: jest.fn(),
  patchInstall: jest.fn(),
  uninstallInstall: jest.fn(),
}))

jest.mock('../Skills', () => () => <div>skills-tab</div>)

jest.mock('../../hooks/usePermission', () => ({
  usePermission: () => perm,
}))

import Capabilities from '../Capabilities'
import MyInstalls from '../MyInstalls'
import {
  fetchPublicCapability, listInstalls, listPublicAssets, subscribeCapability,
} from '../../services/capabilities'

const fetchList = listPublicAssets as jest.Mock
const fetchCard = fetchPublicCapability as jest.Mock
const subscribe = subscribeCapability as jest.Mock
const installs = listInstalls as jest.Mock

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

beforeEach(() => {
  perm.isPlatformAdmin = false
  perm.role = 'operator'
  fetchList.mockReset()
  fetchCard.mockReset()
  subscribe.mockReset()
  installs.mockReset()
  Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
})

test('GWT-U11.2 closed flag copy is 能力市场未开放, not empty shelf', async () => {
  fetchList.mockResolvedValue({
    items: [], total: 0, market_closed: true, empty: true, message: MARKET_CLOSED,
  })
  renderShelf()
  expect(await screen.findByText(MARKET_CLOSED)).toBeInTheDocument()
  expect(screen.queryByText('开放后，已上架的能力会出现在这里。')).not.toBeInTheDocument()
  expect(screen.queryByText(EMPTY_SHELF)).not.toBeInTheDocument()
  expect(screen.queryByText(LOAD_FAIL)).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '订阅' })).not.toBeInTheDocument()
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

test('GWT-U10.4 coming_soon has 预告 and no subscribe button', async () => {
  fetchList.mockResolvedValue({
    items: [item({
      name: 'soon-review', title: '预告审查', listing_state: 'coming_soon', subscribable: false,
    })],
    total: 1, market_closed: false,
  })
  renderShelf()
  expect(await screen.findByText('预告审查')).toBeInTheDocument()
  expect(screen.getByText('预告')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '订阅' })).not.toBeInTheDocument()
  expect(screen.queryByText(EMPTY_SHELF)).not.toBeInTheDocument()
})

test('GWT-U10.3 readonly subscribe is disabled and does not POST', async () => {
  perm.role = 'viewer'
  fetchList.mockResolvedValue({ items: [item()], total: 1, market_closed: false })
  renderShelf()
  const btn = await screen.findByRole('button', { name: '订阅' })
  expect(btn).toBeDisabled()
  expect(btn).toHaveAttribute('title', READONLY_SUBSCRIBE)
  fireEvent.click(btn)
  expect(subscribe).not.toHaveBeenCalled()
})

test('GWT-U10.1 subscribe plugin appears in 我的安装 without children', async () => {
  fetchList.mockResolvedValue({
    items: [item({
      asset_type: 'plugin', name: 'u101-plug', title: '父插件', listing_state: 'listed',
    })],
    total: 1, market_closed: false,
  })
  fetchCard.mockResolvedValue({
    name: 'u101-plug', asset_type: 'plugin',
    hosts: ['grok', 'zcode', 'kimi', 'claude'], subscribable: true,
  })
  subscribe.mockResolvedValue({ created: true, message: '已订阅到 Grok', host: 'grok', asset_id: 9 })
  installs.mockResolvedValue({ total: 1, items: [installRow()] })
  renderShelf()
  fireEvent.click(await screen.findByRole('button', { name: '订阅' }))
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

test('tenant company admin has no market switch and no listing tabs', async () => {
  perm.role = 'admin'
  perm.isAdmin = true
  fetchList.mockResolvedValue({ items: [], total: 0, market_closed: true, message: MARKET_CLOSED })
  renderShelf()
  expect(await screen.findByText(MARKET_CLOSED)).toBeInTheDocument()
  expect(screen.queryByTestId('power-market-switch')).not.toBeInTheDocument()
  expect(screen.queryByRole('tab', { name: '源' })).not.toBeInTheDocument()
  expect(screen.queryByRole('tab', { name: '目录' })).not.toBeInTheDocument()
  expect(screen.queryByText('上架')).not.toBeInTheDocument()
})

test('GWT-M40 tenant shelf has no author portal and no seven-leaf', async () => {
  fetchList.mockResolvedValue({ items: [item()], total: 1, market_closed: false })
  renderShelf()
  expect(await screen.findByRole('button', { name: '订阅' })).toBeInTheDocument()
  expect(screen.queryByText('投稿')).not.toBeInTheDocument()
  expect(screen.queryByText('成为作者')).not.toBeInTheDocument()
  expect(screen.queryByText('发布到能力市场')).not.toBeInTheDocument()
  expect(screen.queryByTestId('governance-shell')).not.toBeInTheDocument()
  expect(screen.queryByRole('tab', { name: '源' })).not.toBeInTheDocument()
  expect(document.body.textContent || '').not.toContain('当前可买')
})
