/**
 * T-04 / FR-U02：工人句与配额句不得混用；入队成功见「已入队」。
 */
import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

jest.mock('../../services/spiders', () => ({
  runSpider: jest.fn().mockResolvedValue({
    id: 7, spider_name: 'example', status: 'pending', result_count: 0,
  }),
}))

jest.mock('../../services/usage', () => ({
  fetchUpgradeIntent: jest.fn().mockResolvedValue({
    action: 'contact_admin', product: 'plan_pro', checkout_path: null, message: '请联系本企业管理员开通',
  }),
}))

// eslint-disable-next-line import/first
import { TaskModal } from './TaskModal'
import { runSpider } from '../../services/spiders'
import {
  ENQUEUED_COPY,
  PLAN_FULL_COPY,
  SPIDER_WORKER_OFFLINE_COPY,
  STORAGE_CTA,
  TASK_QUOTA_LIMIT_CODE,
  UPGRADE_CTA,
  VIEW_NODES_TEXT,
} from '../../constants/collectCopy'
import type { SpiderRegistry } from './types'

const registry: SpiderRegistry = {
  types: [{ type: 'web', label: 'Web 网页', fields: [] }],
  spiders: [{ name: 'example', title: '示例', type: 'web' }],
}

const onSubmitSuccess = jest.fn()
const onCancel = jest.fn()

function renderModal(workerOffline?: boolean) {
  return render(
    <MemoryRouter initialEntries={['/spiders/tasks']}>
      <Routes>
        <Route
          path="/spiders/tasks"
          element={(
            <TaskModal
              visible
              registry={registry}
              spiderMap={{ example: { title: '示例', type: 'web' } }}
              templates={[]}
              workerOffline={workerOffline}
              onSubmitSuccess={onSubmitSuccess}
              onCancel={onCancel}
            />
          )}
        />
        <Route path="/spiders/nodes" element={<div>nodes-page-probe</div>} />
        <Route path="/data" element={<div>data-page-probe</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

const openModalSelect = (idx: number) => {
  // eslint-disable-next-line testing-library/no-node-access
  const modal = document.querySelector('.ant-modal') as HTMLElement
  fireEvent.mouseDown(modal.querySelectorAll('.ant-select')[idx])
}

const clickDropdownOption = async (text: string) => {
  const node = await waitFor(() => {
    // eslint-disable-next-line testing-library/no-node-access
    const hit = Array.from(document.querySelectorAll('.ant-select-item-option-content'))
      .find((e) => (e.textContent || '').trim() === text)
    if (!hit) throw new Error(`option not found: ${text}`)
    return hit
  })
  // eslint-disable-next-line testing-library/no-node-access
  fireEvent.click(node.closest('.ant-select-item-option') as HTMLElement)
}

beforeEach(() => {
  ;(runSpider as jest.Mock).mockReset()
  ;(runSpider as jest.Mock).mockResolvedValue({
    id: 7, spider_name: 'example', status: 'pending', result_count: 0,
  })
  onSubmitSuccess.mockClear()
  onCancel.mockClear()
})

test('GWT-U02.1：0 工人提交被拦住——未入队、工人锁句、查看节点，无配额句', async () => {
  renderModal(true)
  expect(screen.getByText('新增采集任务')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /提交任务/ }))

  expect(await screen.findByText(SPIDER_WORKER_OFFLINE_COPY)).toBeInTheDocument()
  expect(screen.queryByText(PLAN_FULL_COPY)).toBeNull()
  expect(screen.getByText('新增采集任务')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: VIEW_NODES_TEXT }))
  expect(await screen.findByText('nodes-page-probe')).toBeInTheDocument()

  expect(runSpider).not.toHaveBeenCalled()
  expect(screen.queryByText(ENQUEUED_COPY)).toBeNull()
  expect(onSubmitSuccess).not.toHaveBeenCalled()
})

test('GWT-U01.1 有工人提交成功见已入队', async () => {
  renderModal(false)
  openModalSelect(0)
  await clickDropdownOption('示例（example）')
  fireEvent.click(screen.getByRole('button', { name: /提交任务/ }))

  expect(await screen.findByText(ENQUEUED_COPY)).toBeInTheDocument()
  expect(runSpider).toHaveBeenCalledTimes(1)
  expect(onSubmitSuccess).toHaveBeenCalledTimes(1)
})

test('GWT-U02.2 storage full: 已达配额上限 + 去结果库, not worker', async () => {
  ;(runSpider as jest.Mock).mockRejectedValueOnce({
    response: {
      status: 400,
      data: {
        code: TASK_QUOTA_LIMIT_CODE,
        message: `${PLAN_FULL_COPY}。${STORAGE_CTA}`,
        data: { dimension: 'storage', cta: STORAGE_CTA },
      },
    },
  })
  renderModal(false)
  openModalSelect(0)
  await clickDropdownOption('示例（example）')
  fireEvent.click(screen.getByRole('button', { name: /提交任务/ }))

  expect(await screen.findByText(PLAN_FULL_COPY)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: STORAGE_CTA })).toHaveAttribute('href', '/data')
  expect(screen.queryByText(SPIDER_WORKER_OFFLINE_COPY)).toBeNull()
  expect(onSubmitSuccess).not.toHaveBeenCalled()
  expect(document.body.textContent).not.toContain('QUOTA_EXCEEDED')
  expect(document.body.textContent).not.toContain('当前可买')
})

test('GWT-U02.4 token full on submit: 已达配额上限 + 申请提升, not worker', async () => {
  ;(runSpider as jest.Mock).mockRejectedValueOnce({
    response: {
      status: 400,
      data: {
        code: TASK_QUOTA_LIMIT_CODE,
        message: `${PLAN_FULL_COPY}。${UPGRADE_CTA}`,
        data: { dimension: 'tokens', cta: UPGRADE_CTA },
      },
    },
  })
  renderModal(false)
  openModalSelect(0)
  await clickDropdownOption('示例（example）')
  fireEvent.click(screen.getByRole('button', { name: /提交任务/ }))

  expect(await screen.findByText(PLAN_FULL_COPY)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: UPGRADE_CTA })).toBeInTheDocument()
  expect(screen.queryByText(SPIDER_WORKER_OFFLINE_COPY)).toBeNull()
  expect(screen.queryByRole('button', { name: '申请提升配额' })).toBeNull()
  expect(onSubmitSuccess).not.toHaveBeenCalled()
})
