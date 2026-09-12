/**
 * T-18 / FR-85 GWT-85.2：0 在线工人时新建任务提交被拦住（单支，无「提交后立即可见」）。
 * 拦 = runSpider 未被调用（任务未入队）、不出现「正在排队执行」、未报成功；
 * 提示句在场且含「去节点」入口。有工人/加载中（workerOffline=false）不拦。
 */
import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

jest.mock('../../services/spiders', () => ({
  runSpider: jest.fn().mockResolvedValue({
    id: 7, spider_name: 'example', status: 'pending', result_count: 0,
  }),
}))

// eslint-disable-next-line import/first
import { TaskModal } from './TaskModal'
import { runSpider } from '../../services/spiders'
import { NO_WORKER_SUBMIT_BLOCKED_COPY } from './copy'
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
      </Routes>
    </MemoryRouter>,
  )
}

/** antd v6：Select 无 .ant-select-selector，mousedown 目标是 .ant-select 根（弹窗内定位） */
const openModalSelect = (idx: number) => {
  // eslint-disable-next-line testing-library/no-node-access
  const modal = document.querySelector('.ant-modal') as HTMLElement
  fireEvent.mouseDown(modal.querySelectorAll('.ant-select')[idx])
}

/** antd v6：按选项内容定位下拉项点击（role=option 在 jsdom 不可靠） */
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
  ;(runSpider as jest.Mock).mockClear()
  onSubmitSuccess.mockClear()
  onCancel.mockClear()
})

test('T-18 GWT-85.2：0 工人提交被拦住——未入队、无「正在排队执行」、提示句含「去节点」', async () => {
  renderModal(true)
  expect(screen.getByText('新增采集任务')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /提交任务/ }))

  // 提示句在场 + 去节点入口打开节点页；弹窗保持打开（未关、未入队、未报成功）
  expect(await screen.findByText(NO_WORKER_SUBMIT_BLOCKED_COPY)).toBeInTheDocument()
  expect(screen.getByText('新增采集任务')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /去节点/ }))
  expect(await screen.findByText('nodes-page-probe')).toBeInTheDocument()

  expect(runSpider).not.toHaveBeenCalled()
  expect(screen.queryByText(/正在排队执行/)).toBeNull()
  expect(onSubmitSuccess).not.toHaveBeenCalled()
})

test('T-18 GWT-85.2 前置：有工人/加载中（workerOffline=false）不拦——正常入队并出现排队 toast', async () => {
  renderModal(false)
  openModalSelect(0)
  await clickDropdownOption('示例（example）')
  fireEvent.click(screen.getByRole('button', { name: /提交任务/ }))

  expect(await screen.findByText(/正在排队执行/)).toBeInTheDocument()
  expect(runSpider).toHaveBeenCalledTimes(1)
  expect(runSpider).toHaveBeenCalledWith('example', expect.any(String), 'normal')
  expect(onSubmitSuccess).toHaveBeenCalledTimes(1)
})
