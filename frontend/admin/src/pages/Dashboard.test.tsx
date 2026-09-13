/**
 * 仪表盘零任务引导（T-05 / GWT-07.5）：第一步到 /llm，不到 /newapi。
 * T-17 / FR-84（GWT-84.1/84.2）：统计失败=失败句+重试、卡片不得用 0 冒充没跑过；
 * 真 0 保留引导句与「近 7 日还没有运行记录。」，不落「暂无采集结果/暂无质量评分数据」死胡同。
 */
import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
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
import { fetchAdminStats, fetchQualityReport, fetchRecentCompletedTasks } from '../services/admin'

function Where() {
  const loc = useLocation()
  return <div data-testid="where">{loc.pathname}</div>
}

function renderDashboard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/dashboard']}>
        <Routes>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/llm" element={<Where />} />
          <Route path="/newapi" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

test('zero-task first step goes to /llm not /newapi', async () => {
  renderDashboard()
  expect(await screen.findByText(/还没有采集任务/)).toBeInTheDocument()
  const llm = await screen.findByRole('button', { name: /LLM 配置/ })
  expect(screen.queryByText(/中转站/)).not.toBeInTheDocument()
  fireEvent.click(llm)
  expect(await screen.findByTestId('where')).toHaveTextContent('/llm')
})

test('GWT-84.1 stats failure: failure sentence + retry, no zero cards faking never-ran', async () => {
  ;(fetchAdminStats as jest.Mock).mockRejectedValueOnce(new Error('boom'))
  renderDashboard()
  expect(await screen.findByText('仪表盘加载失败。检查网络后重试。')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /重\s*试/ })).toBeInTheDocument()
  // 失败后卡片不得继续显示 0 冒充没跑过（GWT-84.1 点名）
  expect(screen.queryByText('任务总数')).not.toBeInTheDocument()
  expect(screen.queryByText('近 7 日采集结果')).not.toBeInTheDocument()
  // 失败也不是真 0：引导句不出现
  expect(screen.queryByText(/还没有采集任务/)).not.toBeInTheDocument()
})

test('GWT-84.2 true zero keeps onboarding + chart empty sentence, no dead-end 暂无 copy', async () => {
  renderDashboard()
  expect(await screen.findByText(/还没有采集任务/)).toBeInTheDocument()
  expect(screen.getAllByText('近 7 日还没有运行记录。').length).toBeGreaterThan(0)
  const copy = document.body.textContent || ''
  expect(copy).not.toMatch(/暂无采集结果/)
  expect(copy).not.toMatch(/暂无质量评分数据/)
  expect(copy).not.toMatch(/暂无质量分布数据/)
})

test('GWT-84.1 quality report local failure stays card-local with retry, stats still render', async () => {
  ;(fetchRecentCompletedTasks as jest.Mock).mockResolvedValueOnce([9])
  ;(fetchQualityReport as jest.Mock).mockRejectedValueOnce(new Error('quality down'))
  renderDashboard()
  // 主统计不受局部卡失败拖垮
  expect(await screen.findByText('任务总数')).toBeInTheDocument()
  // 局部卡失败 = 卡内错误 + 重试（不是「暂无质量评分数据」死胡同）；两张质量卡各一处
  const cardFailures = await screen.findAllByText('质量报告加载失败。检查网络后重试。')
  expect(cardFailures).toHaveLength(2)
  expect(screen.getAllByRole('button', { name: /重\s*试/ }).length).toBeGreaterThan(0)
})
