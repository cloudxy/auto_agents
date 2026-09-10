/**
 * T-21：/skills 到达能力市场且已筛技能；非法类型失败；无「专家」类型名。
 */
import React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

jest.mock('../services/capabilities', () => ({
  listPublicAssets: jest.fn().mockResolvedValue({
    items: [
      { name: 'alpha', title: '阿尔法技能', description: '官方推荐技能', category: 'dev-tools', status: 'recommended', tier: 'S', score: 8.6, asset_type: 'skill' },
    ],
  }),
}))

import Capabilities from './Capabilities'

function renderSquare(path: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Capabilities />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

test('old /skills address lands on market filtered to skill (GWT-30.2)', async () => {
  renderSquare('/skills')
  expect(screen.getByRole('heading', { name: '能力市场' })).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: '技能' })).toHaveAttribute('aria-selected', 'true')
  expect(await screen.findByText('阿尔法技能')).toBeInTheDocument()
  expect(screen.queryByRole('tab', { name: '专家' })).not.toBeInTheDocument()
  expect(screen.getByRole('tab', { name: '智能体' })).toBeInTheDocument()
})

test('bogus type fails instead of showing skill list (GWT-44.2)', () => {
  renderSquare('/capabilities?type=bogus')
  expect(screen.getByText('没有这种类型')).toBeInTheDocument()
  expect(screen.queryByText('阿尔法技能')).not.toBeInTheDocument()
})
