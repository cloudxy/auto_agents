/**
 * T-28 治理台七叶：GWT-37.1…37.6 / 40.1…40.3。
 */
import React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import {
  AGENT_EMPTY, BULK_LIST, CATALOG_EMPTY, COMMAND_EMPTY, ENABLE_HOST, HOST_RUNNING,
  GOVERNANCE_PAGE_SIZE, LIST_CHILD, LISTED_NE_VERIFY, MERGED,
  NEED_PLATFORM_MARKET, OPEN_IN_CATALOG, SOURCE_EMPTY, SUB_NE_HOST, TAB_LABELS,
  TEAM_EMPTY, catalogFocusCopy,
} from './market/marketCopy'
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
  listSources: jest.fn().mockResolvedValue({ total: 0, items: [] }),
  registerSource: jest.fn(),
  syncSource: jest.fn(),
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
  listPublicAssets: jest.fn().mockResolvedValue({ items: [], total: 0, market_closed: false }),
  getPowerMarket: jest.fn().mockResolvedValue({ enabled: true }),
  putPowerMarket: jest.fn(),
}))

jest.mock('./Skills', () => () => <div>skills-tab</div>)

jest.mock('../hooks/usePermission', () => ({
  usePermission: () => perm,
}))

import Capabilities from './Capabilities'
import { getPlugin, listAssets, patchListing } from '../services/capabilities'

const list = listAssets as jest.Mock
const patch = patchListing as jest.Mock
const pluginDetail = getPlugin as jest.Mock

const row = (over: Partial<AssetRow> = {}): AssetRow => ({
  id: 1,
  asset_type: 'skill',
  name: 'demo-skill',
  title: '演示',
  category: 'cat',
  status: 'stable',
  sync_state: 'ok',
  listing_state: 'unlisted',
  listed_at: null,
  source_type: 'self_built',
  ...over,
})

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/capabilities']}>
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
  patch.mockReset()
  pluginDetail.mockReset()
  list.mockResolvedValue({ total: 0, items: [] })
})

test('GWT-37.1 seven tabs and no 专家 agent leaf', async () => {
  renderPage()
  expect(await screen.findByText(CATALOG_EMPTY)).toBeInTheDocument()
  expect(await screen.findByTestId('power-market-switch')).toBeInTheDocument()
  for (const label of TAB_LABELS) {
    expect(screen.getByRole('tab', { name: label })).toBeInTheDocument()
  }
  expect(screen.queryByRole('tab', { name: /^专家$/ })).not.toBeInTheDocument()
  expect(document.querySelector('.market-tabs')).toBeTruthy()
  expect(document.body.textContent || '').not.toContain('当前可买')
})

test('GWT-37.2 command empty is actionable not git path', async () => {
  renderPage()
  fireEvent.click(screen.getByRole('tab', { name: '命令' }))
  expect(await screen.findByText(COMMAND_EMPTY)).toBeInTheDocument()
  expect(document.body.textContent).not.toMatch(/capability-library/)
  expect(document.body.textContent).not.toMatch(/git /)
  expect(screen.getByRole('button', { name: '去源叶' })).toBeInTheDocument()
})

test('GWT-37.3 platform admin listing switch is enabled on governance shell', async () => {
  list.mockResolvedValue({ total: 1, items: [row()] })
  renderPage()
  const group = await screen.findByRole('group', { name: '上架 demo-skill' })
  expect(group.querySelector('input')).not.toBeDisabled()
  expect(screen.queryByText(NEED_PLATFORM_MARKET)).not.toBeInTheDocument()
  expect(screen.getByTestId('governance-shell')).toBeInTheDocument()
})

test('GWT-37.4 merged sentence keeps listed child', async () => {
  perm.isPlatformAdmin = true
  list.mockResolvedValue({
    total: 2,
    items: [
      row({ id: 1, name: 'dev-team', asset_type: 'plugin', listing_state: 'unlisted' }),
      row({
        id: 2, name: 'kept-child', listing_state: 'listed',
        listed_at: '2026-01-02T00:00:00',
      }),
    ],
  })
  patch.mockRejectedValue({ response: { data: { message: MERGED, code: 'LISTING_MERGED' } } })
  renderPage()
  const group = await screen.findByRole('group', { name: '上架 dev-team' })
  fireEvent.click(within(group).getByText('已上架'))
  expect(await screen.findByText(MERGED)).toBeInTheDocument()
  expect(screen.getByText(/最近上架 2026-01-02T00:00:00/)).toBeInTheDocument()
})

test('GWT-37.5 plugin drawer has no bulk-list control', async () => {
  perm.isPlatformAdmin = true
  list.mockImplementation((type?: string) => {
    if (type === 'plugin') {
      return Promise.resolve({
        total: 1,
        items: [row({ id: 9, name: 'pack-a', asset_type: 'plugin' })],
      })
    }
    return Promise.resolve({ total: 0, items: [] })
  })
  pluginDetail.mockResolvedValue({
    name: 'pack-a', health_status: 'unknown', bundled_skills: ['child-a'], mcp_servers: {},
  })
  renderPage()
  fireEvent.click(screen.getByRole('tab', { name: '插件' }))
  expect(await screen.findByText('pack-a')).toBeInTheDocument()
  fireEvent.click(screen.getByText('详情'))
  expect(await screen.findByText(OPEN_IN_CATALOG)).toBeInTheDocument()
  expect(screen.getByText(LIST_CHILD)).toBeInTheDocument()
  expect(document.body.textContent).not.toContain(BULK_LIST)
})

test('IM-17 open in catalog keeps short name', async () => {
  perm.isPlatformAdmin = true
  list.mockImplementation((type?: string) => {
    if (type === 'plugin') {
      return Promise.resolve({
        total: 1,
        items: [row({ id: 9, name: 'pack-a', asset_type: 'plugin' })],
      })
    }
    return Promise.resolve({
      total: 1,
      items: [row({
        id: 10, name: 'pack-a__child-a', title: 'child-a', asset_type: 'skill',
      })],
    })
  })
  pluginDetail.mockResolvedValue({
    name: 'pack-a', health_status: 'unknown', bundled_skills: ['child-a'], mcp_servers: {},
  })
  renderPage()
  fireEvent.click(screen.getByRole('tab', { name: '插件' }))
  expect(await screen.findByText('pack-a')).toBeInTheDocument()
  fireEvent.click(screen.getByText('详情'))
  fireEvent.click(await screen.findByText(OPEN_IN_CATALOG))
  expect(await screen.findByText(catalogFocusCopy('child-a'))).toBeInTheDocument()
  expect(screen.getByText('pack-a__child-a')).toBeInTheDocument()
})

test('IM-19 governance catalog table paginates', async () => {
  list.mockResolvedValue({ total: 1, items: [row()] })
  renderPage()
  expect(await screen.findByText('demo-skill')).toBeInTheDocument()
  expect(document.querySelector('.ant-pagination')).toBeTruthy()
  expect(screen.getByText('共 1 条')).toBeInTheDocument()
  expect(GOVERNANCE_PAGE_SIZE).toBe(20)
})

test('GWT-37.6 listed_at remains after unlist in the row', async () => {
  perm.isPlatformAdmin = true
  list.mockResolvedValue({
    total: 1,
    items: [row({ listing_state: 'unlisted', listed_at: '2026-03-01T08:00:00' })],
  })
  renderPage()
  expect(await screen.findByText(/最近上架 2026-03-01T08:00:00/)).toBeInTheDocument()
})

test('GWT-40.1 unknown health still allows listing', async () => {
  perm.isPlatformAdmin = true
  list.mockImplementation((type?: string) => {
    if (type === 'plugin') {
      return Promise.resolve({
        total: 1,
        items: [row({ id: 3, name: 'no-mcp', asset_type: 'plugin' })],
      })
    }
    return Promise.resolve({ total: 0, items: [] })
  })
  renderPage()
  fireEvent.click(screen.getByRole('tab', { name: '插件' }))
  expect(await screen.findByText('no-mcp')).toBeInTheDocument()
  const group = screen.getByRole('group', { name: '上架 no-mcp' })
  expect(group.querySelector('input')).not.toBeDisabled()
  expect(screen.getByText(LISTED_NE_VERIFY)).toBeInTheDocument()
})

test('GWT-40.2 no host-running copy and no enable-host', async () => {
  perm.isPlatformAdmin = true
  list.mockImplementation((type?: string) => {
    if (type === 'plugin') {
      return Promise.resolve({
        total: 1,
        items: [row({ id: 4, name: 'pack-b', asset_type: 'plugin' })],
      })
    }
    return Promise.resolve({ total: 0, items: [] })
  })
  pluginDetail.mockResolvedValue({
    name: 'pack-b', health_status: 'unknown', bundled_skills: [], mcp_servers: {},
  })
  renderPage()
  fireEvent.click(screen.getByRole('tab', { name: '插件' }))
  expect(await screen.findByText('pack-b')).toBeInTheDocument()
  fireEvent.click(screen.getByText('详情'))
  expect(await screen.findByText(SUB_NE_HOST)).toBeInTheDocument()
  expect(document.body.textContent).not.toContain(HOST_RUNNING)
  expect(screen.queryByRole('button', { name: ENABLE_HOST })).not.toBeInTheDocument()
  expect(document.body.textContent).not.toContain(ENABLE_HOST)
})

test('source empty shows register for platform admin', async () => {
  renderPage()
  fireEvent.click(screen.getByRole('tab', { name: '源' }))
  expect(await screen.findByText(SOURCE_EMPTY)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '登记源' })).toBeInTheDocument()
})

test('team empty keeps create for platform admin', async () => {
  perm.isPlatformAdmin = true
  renderPage()
  fireEvent.click(screen.getByRole('tab', { name: '专家团' }))
  expect(await screen.findByText(TEAM_EMPTY)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '组建专家团' })).toBeInTheDocument()
})

test('agent leaf empty is 智能体 not 专家', async () => {
  renderPage()
  fireEvent.click(screen.getByRole('tab', { name: '智能体' }))
  expect(await screen.findByText(AGENT_EMPTY)).toBeInTheDocument()
  expect(screen.queryByRole('columnheader', { name: '专家' })).not.toBeInTheDocument()
})
