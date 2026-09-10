/**
 * T-22：列表可搜可筛；预告无按钮；失败≠空（GWT-31.1…31.5）。
 * GWT-31.6 由服务端 test_q_does_not_surface_unlisted_or_blacklist 持有。
 * 空态 / 筛选空 / 失败三句不得互勾。
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
const FAIL_HINT = '检查网络后重试'
const ILLEGAL = '暂无已发布'

const prefixedSkill = (over: Partial<PublicListItem> = {}): PublicListItem => ({
  asset_type: 'skill',
  name: 'mattpocock-skills__code-review',
  title: '代码审查',
  description: '审查说明',
  category: 'dev-tools',
  tier: 'A',
  score: 8.2,
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
  Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
})

test('GWT-31.1 search hits display name and opens a real detail link', async () => {
  fetchList.mockResolvedValue({ items: [prefixedSkill()] })
  renderMarket('/capabilities?q=代码审查')
  expect(await screen.findByRole('link', { name: '代码审查' })).toHaveAttribute(
    'href',
    '/capabilities/skill/mattpocock-skills__code-review',
  )
  expect(screen.queryByText('mattpocock-skills__code-review')).not.toBeInTheDocument()
  expect(fetchList).toHaveBeenCalledWith(expect.objectContaining({ q: '代码审查' }))
  expect(screen.getByTestId('loc')).toHaveTextContent('/capabilities?q=代码审查')
})

test('GWT-31.1 origin short name search hits prefixed catalog name', async () => {
  fetchList.mockResolvedValue({
    items: [prefixedSkill({ title: '' })],
  })
  renderMarket('/capabilities?q=code-review')
  expect(await screen.findByRole('link', { name: 'code-review' })).toHaveAttribute(
    'href',
    '/capabilities/skill/mattpocock-skills__code-review',
  )
  expect(screen.queryByRole('heading', { name: 'mattpocock-skills__code-review' }))
    .not.toBeInTheDocument()
  expect(fetchList).toHaveBeenCalledWith(expect.objectContaining({ q: 'code-review' }))
})

test('search box writes q into the URL', async () => {
  fetchList.mockResolvedValue({ items: [prefixedSkill()] })
  renderMarket('/capabilities')
  await screen.findByRole('link', { name: '代码审查' })
  fireEvent.change(screen.getByLabelText('搜索能力'), { target: { value: '代码审查' } })
  fireEvent.click(screen.getByRole('button', { name: '搜索' }))
  expect(screen.getByTestId('loc')).toHaveTextContent('q=')
  expect(decodeURIComponent(screen.getByTestId('loc').textContent || '')).toContain('q=代码审查')
})

test('GWT-31.2 unfiltered empty is 还没有上架的能力, not 暂无已发布', async () => {
  fetchList.mockResolvedValue({ items: [] })
  renderMarket('/capabilities')
  expect(await screen.findByText(EMPTY)).toBeInTheDocument()
  expect(screen.getByText(/已上架且过许可的能力会出现在这里/)).toBeInTheDocument()
  expect(screen.queryByText(FILTER_EMPTY)).not.toBeInTheDocument()
  expect(screen.queryByText(FAIL)).not.toBeInTheDocument()
  expect(screen.queryByText(ILLEGAL)).not.toBeInTheDocument()
  expect(screen.queryByTestId('filter-echo')).not.toBeInTheDocument()
})

test('GWT-31.3 filtered empty is 没有符合条件的能力 plus 清除筛选', async () => {
  fetchList.mockResolvedValue({ items: [] })
  renderMarket('/capabilities?type=skill&q=没有这货&host=kimi&category=none')
  expect(await screen.findByText(FILTER_EMPTY)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '清除筛选' })).toBeInTheDocument()
  const echo = screen.getByTestId('filter-echo')
  expect(echo).toHaveTextContent('类型')
  expect(echo).toHaveTextContent('skill')
  expect(echo).toHaveTextContent('关键词')
  expect(echo).toHaveTextContent('没有这货')
  expect(echo).toHaveTextContent('宿主')
  expect(echo).toHaveTextContent('kimi')
  expect(echo).toHaveTextContent('分类')
  expect(echo).toHaveTextContent('none')
  expect(screen.queryByText(EMPTY)).not.toBeInTheDocument()
  expect(screen.queryByText(FAIL)).not.toBeInTheDocument()
  expect(screen.queryByText(ILLEGAL)).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '清除筛选' }))
  expect(screen.getByTestId('loc')).toHaveTextContent('/capabilities')
  expect(screen.getByTestId('loc').textContent).not.toContain('q=')
})

test('GWT-31.4 load failure is 市场列表加载失败, not empty stock', async () => {
  fetchList.mockRejectedValue(new Error('network down'))
  renderMarket('/capabilities')
  expect(await screen.findByText(FAIL)).toBeInTheDocument()
  expect(screen.getByText(FAIL_HINT)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument()
  expect(screen.queryByText(EMPTY)).not.toBeInTheDocument()
  expect(screen.queryByText(FILTER_EMPTY)).not.toBeInTheDocument()
  expect(screen.queryByText(ILLEGAL)).not.toBeInTheDocument()
  expect(screen.queryByTestId('filter-echo')).not.toBeInTheDocument()
})

test('GWT-31.4 fail fixture must not return empty items as 31.2', async () => {
  fetchList.mockRejectedValue(new Error('boom'))
  renderMarket('/capabilities')
  await screen.findByText(FAIL)
  expect(screen.queryByText(EMPTY)).not.toBeInTheDocument()
  expect(screen.queryByText(FILTER_EMPTY)).not.toBeInTheDocument()
  await expect(fetchList.mock.results[0].value).rejects.toThrow('boom')
})

test('GWT-31.4 filtered URL still fails as load error, not filter-empty', async () => {
  fetchList.mockRejectedValue(new Error('boom'))
  renderMarket('/capabilities?type=skill&q=没有这货&host=kimi&category=none')
  expect(await screen.findByText(FAIL)).toBeInTheDocument()
  expect(screen.queryByText(EMPTY)).not.toBeInTheDocument()
  expect(screen.queryByText(FILTER_EMPTY)).not.toBeInTheDocument()
  expect(screen.queryByTestId('filter-echo')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '清除筛选' })).not.toBeInTheDocument()
})

test('GWT-31.5 coming_soon card shows 预告 and no subscribe button', async () => {
  fetchList.mockResolvedValue({
    items: [prefixedSkill({
      title: '预告审查',
      name: 'soon-review',
      listing_state: 'coming_soon',
      subscribable: false,
    })],
  })
  renderMarket('/capabilities')
  expect(await screen.findByText('预告审查')).toBeInTheDocument()
  expect(screen.getByText('预告')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /订阅/ })).not.toBeInTheDocument()
  expect(screen.queryByRole('link', { name: /订阅/ })).not.toBeInTheDocument()
  expect(screen.queryByText('尚未上架')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '尚未上架' })).not.toBeInTheDocument()
})

test('list sends URL filters and renders mock items without a second client filter', async () => {
  fetchList.mockResolvedValue({
    items: [
      prefixedSkill(),
      prefixedSkill({ name: 'other-review', title: '另一项' }),
    ],
  })
  renderMarket('/capabilities?q=代码审查&host=kimi&category=dev-tools')
  expect(await screen.findByRole('link', { name: '代码审查' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: '另一项' })).toBeInTheDocument()
  expect(fetchList).toHaveBeenCalledTimes(1)
  expect(fetchList).toHaveBeenCalledWith({
    type: undefined,
    q: '代码审查',
    host: 'kimi',
    category: 'dev-tools',
  })
  const args = fetchList.mock.calls[0][0]
  expect(args).not.toHaveProperty('listing_state')
  expect(args).not.toHaveProperty('status')
})

test('type host category stay in the URL and are sent to list_public', async () => {
  fetchList.mockResolvedValue({ items: [prefixedSkill()] })
  renderMarket('/capabilities?type=skill&host=kimi&category=dev-tools')
  await screen.findByText('代码审查')
  expect(fetchList).toHaveBeenCalledWith(expect.objectContaining({
    type: 'skill',
    host: 'kimi',
    category: 'dev-tools',
  }))
  const loc = screen.getByTestId('loc').textContent || ''
  expect(loc).toContain('type=skill')
  expect(loc).toContain('host=kimi')
  expect(loc).toContain('category=dev-tools')
})

test('GWT-43.3 official market has no tenant analytics query surface', async () => {
  fetchList.mockResolvedValue({ items: [prefixedSkill()] })
  renderMarket('/capabilities?type=skill&host=kimi&category=dev-tools')
  expect(await screen.findByRole('link', { name: '代码审查' })).toBeInTheDocument()
  expect(screen.queryByText(/市场分析/)).not.toBeInTheDocument()
  expect(screen.queryByText(/产品事实/)).not.toBeInTheDocument()
  expect(fetchList).toHaveBeenCalledWith(expect.objectContaining({
    type: 'skill', host: 'kimi', category: 'dev-tools',
  }))
})
