/**
 * T-30：命令独立可订卡片（GWT-39.1 / 39.2）。
 * GWT-39.3 由服务端 test_gwt_39_3_unlisted_slash_not_in_public_search 持有。
 * 不是插件 JSON 货架；空态走 GWT-31.3 筛选空。
 */
import React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'

jest.mock('../services/capabilities', () => ({
  listPublicAssets: jest.fn(),
}))

import { listPublicAssets, type PublicListItem } from '../services/capabilities'
import Capabilities from './Capabilities'

const fetchList = listPublicAssets as jest.MockedFunction<typeof listPublicAssets>

const EMPTY = '还没有上架的能力'
const FILTER_EMPTY = '没有符合条件的能力'
const FAIL = '市场列表加载失败'
const JSON_SHELF = ['plugin.json', '"commands"', '/shelf-slash']

const listedCommand = (over: Partial<PublicListItem> = {}): PublicListItem => ({
  asset_type: 'command',
  name: 'pack__run-task',
  title: '跑任务',
  description: '独立命令卡',
  category: 'command',
  slash: 'sdlc',
  listing_state: 'listed',
  subscribable: true,
  ...over,
})

function LocationProbe() {
  const loc = useLocation()
  return <div data-testid="loc">{`${loc.pathname}${loc.search}`}</div>
}

function renderMarket(path: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <LocationProbe />
        <Routes>
          <Route path="/skills" element={<Capabilities />} />
          <Route path="/capabilities" element={<Capabilities />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  fetchList.mockReset()
})

test('GWT-39.1 listed command card appears and opens detail', async () => {
  fetchList.mockResolvedValue({ items: [listedCommand()] })
  renderMarket('/capabilities?type=command')
  const card = await screen.findByRole('link', { name: '跑任务' })
  expect(card).toHaveAttribute('href', '/capabilities/command/pack__run-task')
  expect(screen.getByTestId('command-slash')).toHaveTextContent('/sdlc')
  expect(screen.getByRole('tab', { name: '命令' })).toHaveAttribute('aria-selected', 'true')
  expect(fetchList).toHaveBeenCalledWith(expect.objectContaining({ type: 'command' }))
  const body = document.body.textContent || ''
  JSON_SHELF.forEach((token) => expect(body).not.toContain(token))
  expect(screen.queryByRole('button', { name: /订阅/ })).not.toBeInTheDocument()
})

test('GWT-39.2 command filter empty is 没有符合条件的能力 not plugin JSON', async () => {
  fetchList.mockResolvedValue({ items: [] })
  renderMarket('/capabilities?type=command')
  expect(await screen.findByText(FILTER_EMPTY)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '清除筛选' })).toBeInTheDocument()
  const echo = screen.getByTestId('filter-echo')
  expect(echo).toHaveTextContent('类型')
  expect(echo).toHaveTextContent('command')
  expect(screen.queryByText(EMPTY)).not.toBeInTheDocument()
  expect(screen.queryByText(FAIL)).not.toBeInTheDocument()
  const body = document.body.textContent || ''
  JSON_SHELF.forEach((token) => expect(body).not.toContain(token))
  expect(screen.queryByTestId('command-slash')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '清除筛选' }))
  expect(screen.getByTestId('loc')).toHaveTextContent('/capabilities')
})

test('command tab stays in the URL and is sent to list_public', async () => {
  fetchList.mockResolvedValue({ items: [listedCommand()] })
  renderMarket('/capabilities')
  await screen.findByRole('link', { name: '跑任务' })
  fireEvent.click(screen.getByRole('tab', { name: '命令' }))
  expect(screen.getByTestId('loc').textContent).toContain('type=command')
})
