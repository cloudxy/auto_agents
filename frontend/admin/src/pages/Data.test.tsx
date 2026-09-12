/**
 * 数据中心导出（T-02 / FR-03）：仅 CSV/JSON，单次 100 条，空窗不下载。
 * T-17 / FR-84（GWT-84.1/84.2）：结果/统计加载失败=失败句+重试（统计卡不得 ?? 0）；
 * 真 0=「还没有采集结果。完成一次采集后会显示在这里。」+ 去采集。
 */
import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { message } from 'antd'

jest.mock('../services/spiders', () => ({
  fetchRegistry: jest.fn().mockResolvedValue({ spiders: [], types: [] }),
  searchResults: jest.fn().mockResolvedValue({ items: [], total: 0 }),
  deleteResult: jest.fn(),
  fetchResults: jest.fn().mockResolvedValue({ items: [], total: 0 }),
  exportResults: jest.fn(),
  fetchTaskStore: jest.fn().mockResolvedValue({ targets: [] }),
}))

jest.mock('../services/admin', () => ({
  fetchAdminStats: jest.fn().mockResolvedValue({
    total_tasks: 0, pending: 0, running: 0, completed: 0, failed: 0,
  }),
}))

jest.mock('../components/spider/ResultDrawer', () => ({
  ResultDrawer: () => null,
}))

jest.mock('../hooks/usePermission', () => ({
  usePermission: () => ({
    hasPermission: () => false,
    role: 'operator',
    isAdmin: false,
    permissions: [],
    filteredMenus: [],
  }),
}))

import Data from './Data'
import { searchResults } from '../services/spiders'
import { fetchAdminStats } from '../services/admin'

function Where() {
  const loc = useLocation()
  return <div data-testid="where">{loc.pathname}</div>
}

function renderData() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/data']}>
        <Routes>
          <Route path="/data" element={<Data />} />
          <Route path="/spiders/tasks" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  ;(searchResults as jest.Mock).mockReset()
  ;(searchResults as jest.Mock).mockResolvedValue({ items: [], total: 0 })
  ;(fetchAdminStats as jest.Mock).mockReset()
  ;(fetchAdminStats as jest.Mock).mockResolvedValue({
    total_tasks: 0, pending: 0, running: 0, completed: 0, failed: 0,
  })
  URL.createObjectURL = jest.fn().mockReturnValue('blob:test')
  URL.revokeObjectURL = jest.fn()
})

test('export options have csv/json, copy 单次最多 100 条, no xlsx', async () => {
  renderData()
  expect(await screen.findByText('单次最多 100 条')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /导出/ })).toBeInTheDocument()
  expect(document.body.textContent).not.toMatch(/xlsx/i)
  expect(document.body.textContent).not.toMatch(/Excel/i)
})

test('zero rows: 没有可导出的结果 and no file download', async () => {
  const warn = jest.spyOn(message, 'warning').mockImplementation((() => undefined) as unknown as typeof message.warning)
  renderData()
  await screen.findByText('单次最多 100 条')
  fireEvent.click(screen.getByRole('button', { name: /导出/ }))
  await waitFor(() => {
    expect(warn).toHaveBeenCalledWith('没有可导出的结果')
  })
  expect(URL.createObjectURL).not.toHaveBeenCalled()
  warn.mockRestore()
})

test('GWT-84.2 true zero results: 还没有采集结果 + 去采集 goes to /spiders/tasks', async () => {
  renderData()
  expect(await screen.findByText('还没有采集结果。完成一次采集后会显示在这里。')).toBeInTheDocument()
  expect(screen.queryByText(/加载失败/)).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /去采集/ }))
  expect(await screen.findByTestId('where')).toHaveTextContent('/spiders/tasks')
})

test('GWT-84.1 results load failure: failure sentence + retry, table does not fall to 暂无数据', async () => {
  ;(searchResults as jest.Mock).mockRejectedValueOnce(new Error('network down'))
  renderData()
  expect(await screen.findByText('结果加载失败。检查网络后重试。')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /重\s*试/ })).toBeInTheDocument()
  expect(screen.queryByText(/暂无数据/)).not.toBeInTheDocument()
  expect(screen.queryByText(/还没有采集结果/)).not.toBeInTheDocument()
})

test('GWT-84.1 stats failure: stats cards replaced by failure sentence + retry, results still work', async () => {
  ;(fetchAdminStats as jest.Mock).mockRejectedValueOnce(new Error('stats down'))
  renderData()
  expect(await screen.findByText('统计数据加载失败。检查网络后重试。')).toBeInTheDocument()
  // 统计卡失败不得用 0 冒充（卡片整体不渲染）
  expect(screen.queryByText('任务总数')).not.toBeInTheDocument()
  // 局部失败不拖垮检索区：真 0 空态句照常出现
  expect(await screen.findByText('还没有采集结果。完成一次采集后会显示在这里。')).toBeInTheDocument()
})
