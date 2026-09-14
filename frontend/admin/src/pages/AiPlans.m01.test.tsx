/**
 * T-01 / FR-M01：智能规划未开放金标句；成功只到「方案与试采」。
 * 锁句抄 spec §0.2；禁止「还没有规划」；禁止「已入队」「规划已受理」。
 */
import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { message } from 'antd'

jest.mock('../hooks/usePermission', () => ({
  usePermission: () => mockPerm,
}))

const mockPerm = {
  hasPermission: (code: string) => mockPerm.allow || code === 'menu:ai',
  isAdmin: true,
  role: 'admin' as string,
  permissions: [] as string[],
  permissionsReady: true,
  filteredMenus: [] as unknown[],
  allow: true,
}

jest.mock('../services/ai', () => {
  const actual = jest.requireActual('../services/ai')
  return {
    ...actual,
    fetchAiPlans: jest.fn(),
    createAiPlan: jest.fn(),
    fetchAiPlan: jest.fn(),
    triggerAiPlan: jest.fn(),
    triggerAiTest: jest.fn(),
    registerAiPlan: jest.fn(),
    deleteAiPlan: jest.fn(),
  }
})

jest.mock('../services/spiders', () => ({
  fetchTaskLogs: jest.fn().mockResolvedValue({ status: 'completed', items: [] }),
  runSpider: jest.fn(),
}))

jest.mock('../components/spider/LogDrawer', () => ({ LogDrawer: () => null }))
jest.mock('../components/spider/ResultDrawer', () => ({ ResultDrawer: () => null }))

import AiPlans from './AiPlans'
import { createAiPlan, fetchAiPlans, triggerAiPlan } from '../services/ai'

const GOLD_DISABLED = '智能规划未开放'
const GO_TASKS = '去采集任务'
const STEP_PREVIEW = '方案与试采'

function Where() {
  const loc = useLocation()
  return <div data-testid="where">{loc.pathname}</div>
}

function renderAi() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/ai']}>
        <Routes>
          <Route path="/ai" element={<AiPlans />} />
          <Route path="/spiders/tasks" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const draftPlan = {
  id: 9,
  target_url: 'https://example.com/news',
  status: 'draft',
  plan_json: {
    flow: {
      selectors: [{ name: 'title', type: 'css', expr: 'h1' }],
    },
  },
}

beforeEach(() => {
  mockPerm.allow = true
  mockPerm.role = 'admin'
  mockPerm.hasPermission = () => true
  ;(fetchAiPlans as jest.Mock).mockReset()
  ;(createAiPlan as jest.Mock).mockReset()
  ;(triggerAiPlan as jest.Mock).mockReset()
  ;(fetchAiPlans as jest.Mock).mockResolvedValue({ items: [], total: 0, planning_disabled: false })
  ;(createAiPlan as jest.Mock).mockResolvedValue(draftPlan)
  ;(triggerAiPlan as jest.Mock).mockResolvedValue(draftPlan)
})

test('GWT-M01.2 open while planning disabled: 智能规划未开放, not empty list, 去采集任务', async () => {
  ;(fetchAiPlans as jest.Mock).mockResolvedValue({ items: [], total: 0, planning_disabled: true })
  renderAi()
  expect(await screen.findByText(GOLD_DISABLED)).toBeInTheDocument()
  expect(screen.queryByText('还没有规划')).not.toBeInTheDocument()
  expect(screen.queryByText(/加载失败/)).not.toBeInTheDocument()
  expect(document.body.textContent).not.toContain('QUOTA_EXCEEDED')
  expect(document.body.textContent).not.toContain('当前可买')
  fireEvent.click(screen.getByRole('button', { name: GO_TASKS }))
  expect(await screen.findByTestId('where')).toHaveTextContent('/spiders/tasks')
})

test('GWT-M01.1 submit while disabled: same gold copy in 3s, no plan row, no 已入队', async () => {
  ;(fetchAiPlans as jest.Mock).mockResolvedValue({ items: [], total: 0, planning_disabled: false })
  ;(createAiPlan as jest.Mock).mockRejectedValue({
    response: {
      status: 422,
      data: { code: 'PLANNING_DISABLED', message: GOLD_DISABLED },
    },
  })
  const toast = jest.spyOn(message, 'success').mockImplementation((() => undefined) as never)
  renderAi()
  const url = await screen.findByLabelText('目标页面链接')
  fireEvent.change(url, { target: { value: 'https://example.com/news' } })
  fireEvent.click(screen.getByRole('button', { name: /创建并开始规划/ }))
  expect(await screen.findByText(GOLD_DISABLED)).toBeInTheDocument()
  expect(screen.queryByText('已入队')).not.toBeInTheDocument()
  expect(screen.queryByText('规划已受理')).not.toBeInTheDocument()
  expect(document.body.textContent).not.toContain('QUOTA_EXCEEDED')
  expect(document.body.textContent).not.toMatch(/\b429\b/)
  const previewStep = screen.getByText(STEP_PREVIEW).closest('.ant-steps-item')
  expect(previewStep).not.toHaveClass('ant-steps-item-process')
  expect(toast).not.toHaveBeenCalled()
  toast.mockRestore()
})

test('GWT-M01.3 viewer submit is refused and does not create a plan', async () => {
  mockPerm.allow = false
  mockPerm.role = 'viewer'
  mockPerm.hasPermission = () => false
  renderAi()
  expect(await screen.findByText('当前账号不能开始规划')).toBeInTheDocument()
  const submit = screen.getByRole('button', { name: /创建并开始规划/ })
  expect(submit).toBeDisabled()
  fireEvent.click(submit)
  expect(createAiPlan).not.toHaveBeenCalled()
})

test('GWT-M01.4 success: wizard enters 方案与试采 and list shows the row; no 已入队', async () => {
  ;(fetchAiPlans as jest.Mock).mockImplementation(() =>
    Promise.resolve({
      items: createAiPlan.mock.calls.length ? [draftPlan] : [],
      total: createAiPlan.mock.calls.length ? 1 : 0,
      planning_disabled: false,
    }),
  )
  const toast = jest.spyOn(message, 'success').mockImplementation((() => undefined) as never)
  renderAi()
  fireEvent.change(await screen.findByLabelText('目标页面链接'), {
    target: { value: 'https://example.com/news' },
  })
  fireEvent.click(screen.getByRole('button', { name: /创建并开始规划/ }))
  await waitFor(() => {
    const previewStep = screen.getByText(STEP_PREVIEW).closest('.ant-steps-item')
    expect(previewStep).toHaveClass('ant-steps-item-process')
  })
  expect(screen.queryByText('已入队')).not.toBeInTheDocument()
  expect(screen.queryByText('规划已受理')).not.toBeInTheDocument()
  expect(screen.queryByText(GOLD_DISABLED)).not.toBeInTheDocument()
  expect(toast.mock.calls.flat().join(' ')).not.toMatch(/已入队|规划已受理/)
  fireEvent.click(screen.getByRole('tab', { name: /方案列表/ }))
  expect(await screen.findByText('https://example.com/news')).toBeInTheDocument()
  toast.mockRestore()
})
