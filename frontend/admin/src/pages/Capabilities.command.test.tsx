/**
 * T-30：治理台命令叶可订这一行；插件抽屉不是命令 JSON 货架。不砍命令叶。
 */
import React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import { TAB_LABELS } from './market/marketCopy'
import type { AssetRow } from '../services/capabilities'

const perm = {
  hasPermission: () => true,
  isPlatformAdmin: false,
  role: 'operator',
  isAdmin: false,
  permissions: [] as string[],
  filteredMenus: [] as unknown[],
}

jest.mock('../services/capabilities', () => ({
  listAssets: jest.fn().mockResolvedValue({ total: 0, items: [] }),
  scanPlugins: jest.fn(),
  createTeam: jest.fn(),
  verifyPlugin: jest.fn(),
  patchListing: jest.fn(),
  getPlugin: jest.fn(),
  fetchPublicCapability: jest.fn().mockResolvedValue({
    name: 'pack__run-task',
    hosts: ['grok', 'zcode', 'kimi', 'claude'],
    subscribable: true,
  }),
  subscribeCapability: jest.fn(),
  listInstalls: jest.fn(),
  importAssets: jest.fn(),
  listPublicAssets: jest.fn().mockResolvedValue({ items: [], total: 0, market_closed: false }),
  getPowerMarket: jest.fn().mockResolvedValue({ enabled: true }),
  putPowerMarket: jest.fn(),
}))

jest.mock('./Skills', () => () => <div>skills-tab</div>)

jest.mock('../hooks/usePermission', () => ({
  usePermission: () => perm,
}))

import Capabilities from './Capabilities'
import { getPlugin, listAssets, subscribeCapability } from '../services/capabilities'

const list = listAssets as jest.Mock
const pluginDetail = getPlugin as jest.Mock
const subscribe = subscribeCapability as jest.Mock

const row = (over: Partial<AssetRow> = {}): AssetRow => ({
  id: 1,
  asset_type: 'command',
  name: 'pack__run-task',
  title: '跑任务',
  category: 'command',
  status: 'stable',
  sync_state: 'ok',
  listing_state: 'listed',
  listed_at: '2026-01-01T00:00:00',
  source_type: 'self_built',
  ...over,
})

function renderPage(path = '/capabilities') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/capabilities" element={<Capabilities />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  perm.isPlatformAdmin = true
  list.mockReset()
  pluginDetail.mockReset()
  subscribe.mockReset()
  list.mockResolvedValue({ total: 0, items: [] })
})

test('command tab remains and listed command opens subscribe one row', async () => {
  list.mockImplementation((type?: string) => {
    if (type === 'command') {
      return Promise.resolve({ total: 1, items: [row()] })
    }
    return Promise.resolve({ total: 0, items: [] })
  })
  renderPage()
  expect(screen.getByRole('tab', { name: '命令' })).toBeInTheDocument()
  TAB_LABELS.forEach((label) => {
    expect(screen.getByRole('tab', { name: label })).toBeInTheDocument()
  })
  fireEvent.click(screen.getByRole('tab', { name: '命令' }))
  expect(await screen.findByText('跑任务')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '订阅' }))
  expect(await screen.findByText('订阅 pack__run-task')).toBeInTheDocument()
  expect(subscribe).not.toHaveBeenCalled()
})

test('plugin drawer does not turn commands JSON into a command shelf', async () => {
  perm.isPlatformAdmin = true
  list.mockImplementation((type?: string) => {
    if (type === 'plugin') {
      return Promise.resolve({
        total: 1,
        items: [row({ id: 9, name: 'pack-a', asset_type: 'plugin', title: '包' })],
      })
    }
    return Promise.resolve({ total: 0, items: [] })
  })
  pluginDetail.mockResolvedValue({
    name: 'pack-a',
    health_status: 'unknown',
    bundled_skills: [],
    mcp_servers: {},
    commands: { '/shelf-slash': { prompt: 'from plugin.json' } },
    commands_registered: true,
  })
  renderPage()
  fireEvent.click(screen.getByRole('tab', { name: '插件' }))
  expect(await screen.findByText('pack-a')).toBeInTheDocument()
  fireEvent.click(screen.getByText('详情'))
  expect(await screen.findByText('订阅不等于已在宿主运行')).toBeInTheDocument()
  const copy = document.body.textContent || ''
  expect(copy).not.toContain('/shelf-slash')
  expect(copy).not.toContain('plugin.json')
  expect(copy).not.toContain('from plugin.json')
  expect(screen.queryByRole('link', { name: /shelf-slash/ })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '订阅 /shelf-slash' })).not.toBeInTheDocument()
})
