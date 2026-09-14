/**
 * T-18 值班钥匙叶：签发≠live；权限未就绪禁用「权限加载中」。
 */
import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const perm = { ready: true }
jest.mock('../../hooks/usePermission', () => ({
  usePermission: () => ({
    permissionsReady: perm.ready,
    hasPermission: () => true,
    isPlatformAdmin: true,
    role: 'admin',
    isAdmin: true,
    permissions: [],
    filteredMenus: [],
  }),
}))

jest.mock('../../services/litellmKeys', () => ({
  listLitellmKeys: jest.fn(),
  createLitellmKey: jest.fn(),
}))

import DutyKeysTab from './DutyKeysTab'
import { createLitellmKey, listLitellmKeys } from '../../services/litellmKeys'

const list = listLitellmKeys as jest.Mock
const create = createLitellmKey as jest.Mock

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <DutyKeysTab />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  perm.ready = true
  list.mockReset().mockResolvedValue([])
  create.mockReset()
})

test('GWT-M30.5 permissions loading disables issue as 权限加载中, not unauthorized hide', async () => {
  perm.ready = false
  renderTab()
  expect(await screen.findByTestId('duty-keys')).toBeInTheDocument()
  const btn = screen.getByRole('button', { name: '权限加载中' })
  expect(btn).toBeDisabled()
  expect(screen.queryByText('抱歉您没有权限')).not.toBeInTheDocument()
})

test('GWT-M34 issue shows plaintext once and never 支付已通/live/C2', async () => {
  create.mockResolvedValue({ key_alias: 'ops', token: 'sk-duty-plain' })
  list.mockResolvedValueOnce([]).mockResolvedValue([{ key_alias: 'ops' }])
  renderTab()
  fireEvent.click(await screen.findByRole('button', { name: '签发钥匙' }))
  fireEvent.change(screen.getByLabelText('别名'), { target: { value: 'ops' } })
  fireEvent.click(screen.getByRole('button', { name: /^签\s*发$/ }))
  expect(await screen.findByTestId('duty-key-plaintext')).toHaveTextContent('sk-duty-plain')
  const copy = document.body.textContent || ''
  expect(copy).not.toContain('支付已通')
  expect(copy).not.toContain('当前可买')
  expect(copy).not.toMatch(/\bC2\b/)
  expect(copy).not.toContain('live')
  await waitFor(() => expect(create).toHaveBeenCalledWith('ops'))
})
