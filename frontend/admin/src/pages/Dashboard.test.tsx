/**
 * 仪表盘零任务引导（T-05 / GWT-07.5）：第一步到 /llm，不到 /newapi。
 */
import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'

jest.mock('../services/admin', () => ({
  fetchAdminStats: jest.fn().mockResolvedValue({
    total_tasks: 0, pending: 0, running: 0, completed: 0, failed: 0,
    avg_duration_seconds: null, success_rate: null, total_results: 0,
    daily_tasks: [], daily_results: [], top_spiders: [],
  }),
  fetchQualityReport: jest.fn(),
  fetchRecentCompletedTasks: jest.fn().mockResolvedValue([]),
}))

jest.mock('../store/useAuthStore', () => ({
  useAuthStore: () => ({ user: { username: 'boss' } }),
}))

import Dashboard from './Dashboard'

function Where() {
  const loc = useLocation()
  return <div data-testid="where">{loc.pathname}</div>
}

test('zero-task first step goes to /llm not /newapi', async () => {
  render(
    <MemoryRouter initialEntries={['/dashboard']}>
      <Routes>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/llm" element={<Where />} />
        <Route path="/newapi" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  )
  expect(await screen.findByText(/还没有采集任务/)).toBeInTheDocument()
  const llm = await screen.findByRole('button', { name: /LLM 配置/ })
  expect(screen.queryByText(/中转站/)).not.toBeInTheDocument()
  fireEvent.click(llm)
  expect(await screen.findByTestId('where')).toHaveTextContent('/llm')
})
