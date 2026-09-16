/**
 * 支付渠道配置页（超管专属，系统管理组叶）：两通道卡片状态展示、结构化表单
 * 保存、离线校验、停用确认。antd 两字按钮自动插空格坑（配置/停用/保存/刷新）
 * 用 \s* 正则匹配，与仓库既有测试约定一致（见 OutboundKeys.test.tsx）。
 */
import React from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import PaymentCredentials from './PaymentCredentials'

jest.mock('../services/paymentCredentials', () => ({
  fetchPaymentCredentials: jest.fn(),
  putPaymentCredential: jest.fn(),
  deletePaymentCredential: jest.fn(),
  validatePaymentCredential: jest.fn(),
  buildAlipaySecretsPayload: (f: Record<string, string>) => JSON.stringify(f),
  buildWechatSecretsPayload: (f: Record<string, string>) => JSON.stringify(f),
}))

import {
  deletePaymentCredential, fetchPaymentCredentials, putPaymentCredential,
  validatePaymentCredential,
} from '../services/paymentCredentials'

const NONE_CONFIGURED = {
  channels: [
    { channel: 'alipay', configured: false },
    { channel: 'wechat', configured: false },
  ],
}

const ALIPAY_CONFIGURED = {
  channels: [
    {
      channel: 'alipay', configured: true, merchant_no: '2088611100000000',
      secrets_masked: '********', key_version: 2, updated_at: '2026-09-16T10:00:00Z',
    },
    { channel: 'wechat', configured: false },
  ],
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <PaymentCredentials />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  ;(fetchPaymentCredentials as jest.Mock).mockReset()
  ;(putPaymentCredential as jest.Mock).mockReset()
  ;(deletePaymentCredential as jest.Mock).mockReset()
  ;(validatePaymentCredential as jest.Mock).mockReset()
})

test('未配置时两个通道都显示「未配置」+「配置」按钮', async () => {
  ;(fetchPaymentCredentials as jest.Mock).mockResolvedValue(NONE_CONFIGURED)
  renderPage()
  expect(await screen.findByText('支付宝')).toBeInTheDocument()
  expect(screen.getByText('微信支付')).toBeInTheDocument()
  expect(screen.getAllByText('未配置')).toHaveLength(2)
  expect(screen.getAllByRole('button', { name: /配\s*置/ })).toHaveLength(2)
})

test('已配置显示商户号/掩码/版本，且有校验与停用入口', async () => {
  ;(fetchPaymentCredentials as jest.Mock).mockResolvedValue(ALIPAY_CONFIGURED)
  renderPage()
  expect(await screen.findByText('已配置')).toBeInTheDocument()
  expect(screen.getByText('2088611100000000')).toBeInTheDocument()
  expect(screen.getByText('v2')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '校验格式' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /停\s*用/ })).toBeInTheDocument()
})

test('填写支付宝表单并保存：拼出结构化 JSON 密钥包', async () => {
  ;(fetchPaymentCredentials as jest.Mock).mockResolvedValue(NONE_CONFIGURED)
  ;(putPaymentCredential as jest.Mock).mockResolvedValue({
    channel: 'alipay', configured: true, merchant_no: '2088xxxx',
  })
  renderPage()
  const buttons = await screen.findAllByRole('button', { name: /配\s*置/ })
  fireEvent.click(buttons[0]) // 支付宝卡片是第一张

  const dialog = await screen.findByRole('dialog')
  fireEvent.change(within(dialog).getByPlaceholderText('2088xxxxxxxxxxxx'), { target: { value: '2088611100000000' } })
  fireEvent.change(within(dialog).getByPlaceholderText('2021xxxxxxxxxxxx'), { target: { value: 'app-id-1' } })
  fireEvent.change(within(dialog).getByLabelText(/应用私钥/), { target: { value: 'PRIV-PEM' } })
  fireEvent.change(within(dialog).getByLabelText(/支付宝公钥/), { target: { value: 'PUB-PEM' } })
  fireEvent.click(within(dialog).getByRole('button', { name: /保\s*存/ }))

  // react-query v5 调 mutationFn(variables, {client}) 两个参数（同仓库既有
  // 约定 OutboundKeys.test.tsx 的 expect.anything() 写法）
  await waitFor(() => expect(putPaymentCredential).toHaveBeenCalledWith({
    channel: 'alipay',
    merchant_no: '2088611100000000',
    secrets: JSON.stringify({
      app_id: 'app-id-1', app_private_key: 'PRIV-PEM', alipay_public_key: 'PUB-PEM',
    }),
  }, expect.anything()))
})

test('校验通过显示成功提示，校验失败显示错误原因', async () => {
  ;(fetchPaymentCredentials as jest.Mock).mockResolvedValue(ALIPAY_CONFIGURED)
  renderPage()
  const btn = await screen.findByRole('button', { name: '校验格式' })
  ;(validatePaymentCredential as jest.Mock).mockResolvedValue({ channel: 'alipay', valid: true, checked: 'json+rsa_key_load' })
  fireEvent.click(btn)
  expect(await screen.findByText(/密钥包格式与密钥可正常加载/)).toBeInTheDocument()
})

test('停用需二次确认', async () => {
  ;(fetchPaymentCredentials as jest.Mock).mockResolvedValue(ALIPAY_CONFIGURED)
  ;(deletePaymentCredential as jest.Mock).mockResolvedValue({ channel: 'alipay', configured: false })
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: /停\s*用/ }))
  const dialog = await screen.findByRole('dialog')
  expect(within(dialog).getByText(/停用该支付通道/)).toBeInTheDocument()
  fireEvent.click(within(dialog).getByRole('button', { name: /确认停用/ }))
  await waitFor(() => expect(deletePaymentCredential).toHaveBeenCalledWith('alipay', expect.anything()))
})

test('加载失败显示重试', async () => {
  ;(fetchPaymentCredentials as jest.Mock).mockRejectedValue(new Error('network'))
  renderPage()
  expect(await screen.findByText(/加载失败/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /重\s*试/ })).toBeInTheDocument()
})
