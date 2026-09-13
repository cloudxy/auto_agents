/**
 * T-10 屏 24：超管总开关。失败≠已开/已关。禁「当前可买」。
 */
import React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { message } from 'antd'

jest.mock('../../services/capabilities', () => ({
  getPowerMarket: jest.fn(),
  putPowerMarket: jest.fn(),
}))

import PowerMarketSwitch from './PowerMarketSwitch'
import { getPowerMarket, putPowerMarket } from '../../services/capabilities'

const getSwitch = getPowerMarket as jest.Mock
const putSwitch = putPowerMarket as jest.Mock

function renderSwitch() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <PowerMarketSwitch />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  getSwitch.mockReset()
  putSwitch.mockReset()
})

test('loaded switch shows 能力市场 and can open', async () => {
  getSwitch.mockResolvedValue({ enabled: false })
  putSwitch.mockResolvedValue({ enabled: true })
  const toast = jest.spyOn(message, 'success').mockImplementation(() => undefined as never)
  renderSwitch()
  expect(await screen.findByTestId('power-market-switch')).toBeInTheDocument()
  expect(screen.getByText('能力市场')).toBeInTheDocument()
  expect(document.body.textContent || '').not.toContain('当前可买')
  fireEvent.click(screen.getByRole('switch', { name: '能力市场' }))
  await waitFor(() => expect(putSwitch).toHaveBeenCalledWith(true))
  expect(toast).toHaveBeenCalledWith('已打开能力市场')
  toast.mockRestore()
})

test('read failure is retry copy, not open or closed', async () => {
  getSwitch.mockRejectedValue(new Error('boom'))
  renderSwitch()
  expect(await screen.findByText('市场开关暂时无法读取')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument()
  expect(screen.queryByRole('switch')).not.toBeInTheDocument()
  expect(document.body.textContent || '').not.toContain('当前可买')
})
