/**
 * T-13 / FR-18/19：任务页无工人句与零条目空态（真的 0 条 vs 还在跑）。
 */
import React from 'react'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

jest.mock('../services/admin', () => ({
  fetchNodesPage: jest.fn().mockResolvedValue({ items: [], total: 0 }),
}))

jest.mock('../services/spiders', () => ({
  fetchRegistry: jest.fn().mockResolvedValue({
    types: [],
    spiders: [{ name: 'example', title: '示例', type: 'web' }],
  }),
  fetchTasks: jest.fn(),
  deleteTask: jest.fn(),
  controlTask: jest.fn(),
  fetchTemplates: jest.fn().mockResolvedValue([]),
  fetchResults: jest.fn().mockResolvedValue({ items: [], total: 0 }),
  exportResults: jest.fn(),
  fetchTaskStore: jest.fn().mockResolvedValue({ targets: [] }),
}))

jest.mock('../hooks/usePermission', () => ({
  usePermission: () => ({
    hasPermission: () => true,
    isAdmin: true,
    role: 'admin',
    permissions: [],
    filteredMenus: [],
  }),
}))

jest.mock('../components/spider/ScheduleTab', () => ({ ScheduleTab: () => null }))
jest.mock('../components/spider/FileTab', () => ({ FileTab: () => null }))
jest.mock('../components/spider/AlertRulesTab', () => ({ AlertRulesTab: () => null }))
jest.mock('../components/spider/TemplateTab', () => ({ TemplateTab: () => null }))
jest.mock('../components/spider/TaskModal', () => ({ TaskModal: () => null }))
jest.mock('../components/spider/LogDrawer', () => ({ LogDrawer: () => null }))
jest.mock('../components/spider/ResultDrawer', () => ({ ResultDrawer: () => null }))
jest.mock('../components/spider/TemplateModal', () => ({ TemplateModal: () => null }))
jest.mock('../components/spider/TaskEditModal', () => ({ TaskEditModal: () => null }))

import Spiders from './Spiders'
import { fetchTasks } from '../services/spiders'
import { fetchNodesPage } from '../services/admin'
import {
  SPIDER_WORKER_OFFLINE_COPY,
  STILL_RUNNING_COPY,
  ZERO_ITEMS_DONE_COPY,
} from '../components/spider/copy'

const baseTask = {
  id: 7,
  spider_name: 'example',
  priority: 'normal',
  retry_count: 0,
  params: '{}',
}

function renderSpiders() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Spiders />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

test('test_task_page_offline_or_zero_copy', async () => {
  ;(fetchNodesPage as jest.Mock).mockResolvedValue({ items: [], total: 0 })
  ;(fetchTasks as jest.Mock).mockResolvedValue({
    items: [{
      ...baseTask,
      status: 'pending',
      result_count: 0,
      worker_offline: true,
      error_message: SPIDER_WORKER_OFFLINE_COPY,
    }],
    total: 1,
  })
  const first = renderSpiders()
  expect(await screen.findByText('示例')).toBeInTheDocument()
  expect(screen.getAllByText(SPIDER_WORKER_OFFLINE_COPY).length).toBeGreaterThan(0)
  first.unmount()

  ;(fetchNodesPage as jest.Mock).mockResolvedValue({
    items: [{ worker_id: 'w1' }],
    total: 1,
  })
  ;(fetchTasks as jest.Mock).mockResolvedValue({
    items: [{ ...baseTask, status: 'completed', result_count: 0 }],
    total: 1,
  })
  const done = renderSpiders()
  expect(await screen.findByText('示例')).toBeInTheDocument()
  expect(screen.getByText(ZERO_ITEMS_DONE_COPY)).toBeInTheDocument()
  expect(screen.queryByText(STILL_RUNNING_COPY)).toBeNull()
  done.unmount()

  ;(fetchTasks as jest.Mock).mockResolvedValue({
    items: [{ ...baseTask, status: 'running', result_count: 0 }],
    total: 1,
  })
  renderSpiders()
  expect(await screen.findByText('示例')).toBeInTheDocument()
  expect(screen.getByText(STILL_RUNNING_COPY)).toBeInTheDocument()
  expect(screen.queryByText(ZERO_ITEMS_DONE_COPY)).toBeNull()
})
