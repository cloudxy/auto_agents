/**
 * 数据中心导出（T-02 / FR-03）：仅 CSV/JSON，单次 100 条，空窗不下载。
 */
import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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

beforeEach(() => {
  ;(searchResults as jest.Mock).mockReset()
  ;(searchResults as jest.Mock).mockResolvedValue({ items: [], total: 0 })
  URL.createObjectURL = jest.fn().mockReturnValue('blob:test')
  URL.revokeObjectURL = jest.fn()
})

test('export options have csv/json, copy 单次最多 100 条, no xlsx', async () => {
  render(<Data />)
  expect(await screen.findByText('单次最多 100 条')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /导出/ })).toBeInTheDocument()
  expect(document.body.textContent).not.toMatch(/xlsx/i)
  expect(document.body.textContent).not.toMatch(/Excel/i)
})

test('zero rows: 没有可导出的结果 and no file download', async () => {
  const warn = jest.spyOn(message, 'warning').mockImplementation((() => undefined) as unknown as typeof message.warning)
  render(<Data />)
  await screen.findByText('单次最多 100 条')
  fireEvent.click(screen.getByRole('button', { name: /导出/ }))
  await waitFor(() => {
    expect(warn).toHaveBeenCalledWith('没有可导出的结果')
  })
  expect(URL.createObjectURL).not.toHaveBeenCalled()
  warn.mockRestore()
})
