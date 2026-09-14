/**
 * T-13 / FR-18/19：任务页无工人句与零条目空态（真的 0 条 vs 还在跑）。
 */
import React from 'react'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

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

/** 角色可变容器：默认全有（既有用例不变）；GWT-85.3 只读用例翻 false */
const mockPerm = { allow: true }
jest.mock('../hooks/usePermission', () => ({
  usePermission: () => ({
    hasPermission: () => mockPerm.allow,
    isAdmin: mockPerm.allow,
    role: mockPerm.allow ? 'admin' : 'viewer',
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

/** T-18 / GWT-85.1：以真实路由渲染，「查看节点」跳 /spiders/nodes 由探针捕获 */
function renderSpidersWithRoutes() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/spiders/tasks']}>
        <Routes>
          <Route path="/spiders/tasks" element={<Spiders />} />
          <Route path="/spiders/nodes" element={<div>nodes-page-probe</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => { mockPerm.allow = true })

test('T-34 页级 tab 上提：五 tab 切换只动内容区，任务 pane 状态不丢（GWT-99.1/99.3）', async () => {
  ;(fetchNodesPage as jest.Mock).mockResolvedValue({ items: [{ worker_id: 'w1' }], total: 1 })
  ;(fetchTasks as jest.Mock).mockResolvedValue({
    items: [{ ...baseTask, status: 'completed', result_count: 0 }],
    total: 1,
  })
  renderSpiders()
  expect(await screen.findByText('示例')).toBeInTheDocument()
  // 页名「采集任务」唯一标题在顶栏：页内无标题卡复述（原 Card title）
  expect(screen.queryByText('采集任务')).toBeNull()
  expect(screen.queryByRole('heading')).toBeNull()
  // 五个页级 tab 在场（无 AdminLayout 槽位时 PageHeaderTabs 原位回退，可用性不变）
  for (const label of ['任务列表', '定时任务', '采集方案', '告警规则', '任务模板']) {
    expect(screen.getByRole('tab', { name: new RegExp(label) })).toBeInTheDocument()
  }
  // 切到定时任务：任务 pane 隐藏（display 切换、不卸载）；切回内容仍在（GWT-99.3）
  fireEvent.click(screen.getByRole('tab', { name: /定时任务/ }))
  expect(screen.getByText('示例')).not.toBeVisible()
  fireEvent.click(screen.getByRole('tab', { name: /任务列表/ }))
  expect(screen.getByText('示例')).toBeVisible()
})

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

test('T-18 GWT-85.1：0 工人打开任务页——「不会出数」+「查看节点」打开节点页（加载中不出横幅）', async () => {
  ;(fetchTasks as jest.Mock).mockResolvedValue({
    items: [{ ...baseTask, status: 'completed', result_count: 0 }],
    total: 1,
  })
  // 单渲染走完「在途 → 真 0」：节点数据在途（未知/加载中）时不显示横幅、不拦
  let resolveNodes!: (v: { items: { worker_id: string }[]; total: number }) => void
  const nodesDeferred = new Promise<{ items: { worker_id: string }[]; total: number }>(
    (resolve) => { resolveNodes = resolve },
  )
  ;(fetchNodesPage as jest.Mock).mockImplementation(() => nodesDeferred)
  renderSpidersWithRoutes()
  expect(await screen.findByText('示例')).toBeInTheDocument()
  expect(screen.queryByText(SPIDER_WORKER_OFFLINE_COPY)).toBeNull()

  // 真 0（接口成功且 0 节点）：横幅句 + 去节点按钮，点击打开节点页
  await act(async () => { resolveNodes({ items: [], total: 0 }) })
  expect(await screen.findByText(SPIDER_WORKER_OFFLINE_COPY)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /查看节点/ }))
  expect(await screen.findByText('nodes-page-probe')).toBeInTheDocument()
})

test('T-18 GWT-85.3：只读成员打开采集任务——无提交入口（既有角色显隐仍真）', async () => {
  mockPerm.allow = false
  ;(fetchNodesPage as jest.Mock).mockResolvedValue({
    items: [{ worker_id: 'w1' }],
    total: 1,
  })
  ;(fetchTasks as jest.Mock).mockResolvedValue({
    items: [{ ...baseTask, status: 'completed', result_count: 0 }],
    total: 1,
  })
  renderSpiders()
  expect(await screen.findByText('示例')).toBeInTheDocument()
  // 写入口全部隐藏：新增任务 / 再次运行 / 收藏
  expect(screen.queryByRole('button', { name: /新增任务/ })).toBeNull()
  expect(screen.queryByRole('button', { name: /再次运行/ })).toBeNull()
  expect(screen.queryByRole('button', { name: /收\s*藏/ })).toBeNull()
  // 读操作仍在（页面本身可用，失败≠空）
  expect(screen.getByRole('button', { name: /刷\s*新/ })).toBeInTheDocument()
  expect(screen.getByText('当前账号不能提交采集')).toBeInTheDocument()
})

test('GWT-M03.2 empty free tenant: submit entry visible, no paywall/subscribe/relay gate', async () => {
  ;(fetchNodesPage as jest.Mock).mockResolvedValue({
    items: [{ worker_id: 'w1' }],
    total: 1,
  })
  ;(fetchTasks as jest.Mock).mockResolvedValue({ items: [], total: 0 })
  renderSpiders()
  expect((await screen.findAllByRole('button', { name: /新增任务/ })).length).toBeGreaterThan(0)
  const copy = document.body.textContent || ''
  expect(copy).not.toContain('请先开通专业档')
  expect(copy).not.toContain('请先订阅能力')
  expect(copy).not.toContain('请先开通中转')
  expect(copy).not.toContain('当前可买')
})

