/**
 * T-12 超管产品事实查询页：可按企业/事件过滤；不是租户分析入口。
 */
import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

jest.mock('../services/productEvents', () => ({
  listProductEvents: jest.fn(),
}))

import { listProductEvents } from '../services/productEvents'
import ProductEvents from './ProductEvents'

const list = listProductEvents as jest.Mock

const renderEvents = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ProductEvents />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  list.mockReset()
  list.mockResolvedValue({
    total: 1,
    timezone: 'Asia/Shanghai',
    items: [{
      id: 1,
      occurred_at: '2026-09-01T00:00:00',
      event_name: 'task_completed',
      tenant_id: 9,
      actor_user_id: 2,
      anonymous_id: null,
      role: 'operator',
      props: { spider: 'example', result_count: 3, is_marketplace_candidate: false },
      created_at: '2026-09-01T00:00:01',
    }],
  })
})

test('superadmin events page lists facts by occurred time (GWT-15.1 shell)', async () => {
  renderEvents()
  expect(screen.getByText(/仅平台超管/)).toBeInTheDocument()
  expect(screen.getByText(/Asia\/Shanghai/)).toBeInTheDocument()
  expect(await screen.findByText('task_completed', {}, { timeout: 15000 })).toBeInTheDocument()
  fireEvent.change(screen.getByPlaceholderText('如 market_subscribe_succeeded'), {
    target: { value: 'market_subscribe_succeeded' },
  })
  fireEvent.click(screen.getByRole('button', { name: /查\s*询/ }))
  await waitFor(() => expect(list.mock.calls.length).toBeGreaterThan(1))
  const last = list.mock.calls[list.mock.calls.length - 1][0]
  expect(last.event_name).toBe('market_subscribe_succeeded')
})
