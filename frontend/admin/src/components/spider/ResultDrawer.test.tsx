/**
 * 任务结果抽屉导出（T-02 / FR-03）：CSV/JSON 按钮，无 xlsx，空窗不下载。
 */
import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { message } from 'antd'
import type { Task } from './types'

jest.mock('../../services/spiders', () => ({
  fetchResults: jest.fn().mockResolvedValue({ items: [], total: 0 }),
  exportResults: jest.fn(),
  fetchTaskStore: jest.fn().mockResolvedValue({ targets: [] }),
}))

jest.mock('antd', () => {
  const React = require('react')
  const actual = jest.requireActual('antd')
  const Drawer = (props: { children?: unknown; footer?: unknown; title?: unknown; open?: boolean }) => {
    if (!props.open) return null
    return React.createElement(
      'div',
      null,
      React.createElement('div', null, props.title),
      props.children,
      React.createElement('div', null, props.footer),
    )
  }
  return { ...actual, Drawer }
})

import { ResultDrawer } from './ResultDrawer'
import { fetchResults, exportResults } from '../../services/spiders'

const task: Task = {
  id: 9,
  spider_name: 'example',
  status: 'completed',
  priority: 'normal',
  result_count: 0,
}

beforeEach(() => {
  ;(fetchResults as jest.Mock).mockReset()
  ;(exportResults as jest.Mock).mockReset()
  ;(fetchResults as jest.Mock).mockResolvedValue({ items: [], total: 0 })
  URL.createObjectURL = jest.fn().mockReturnValue('blob:test')
  URL.revokeObjectURL = jest.fn()
})

test('lists csv/json only, copy 单次最多 100 条, no xlsx', async () => {
  render(<ResultDrawer task={task} spiderMap={{}} onClose={() => undefined} />)
  expect(await screen.findByText('单次最多 100 条')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /导出 CSV/ })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /导出 JSON/ })).toBeInTheDocument()
  expect(document.body.textContent).not.toMatch(/xlsx/i)
  expect(document.body.textContent).not.toMatch(/Excel/i)
})

test('zero rows: 没有可导出的结果, exportResults not called', async () => {
  const warn = jest.spyOn(message, 'warning').mockImplementation((() => undefined) as unknown as typeof message.warning)
  render(<ResultDrawer task={task} spiderMap={{}} onClose={() => undefined} />)
  await waitFor(() => expect(fetchResults).toHaveBeenCalled())
  fireEvent.click(screen.getByRole('button', { name: /导出 CSV/ }))
  await waitFor(() => {
    expect(warn).toHaveBeenCalledWith('没有可导出的结果')
  })
  expect(exportResults).not.toHaveBeenCalled()
  expect(URL.createObjectURL).not.toHaveBeenCalled()
  warn.mockRestore()
})
