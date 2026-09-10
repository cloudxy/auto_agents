/**
 * T-25 订阅弹窗：宿主两态、无礼包句、回跳不自动 POST。
 * IM-06 冻结句按 code 分支。IM-07 四宿主位始终在，[] = 全禁用。
 */
import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { message } from 'antd'

jest.mock('../services/capabilities', () => ({
  fetchPublicCapability: jest.fn(),
  subscribeCapability: jest.fn(),
}))

import SubscribeModal, {
  COPY_BY_CODE,
  formErrorFromCode,
  hostNote,
  successCopy,
} from './SubscribeModal'
import { fetchPublicCapability, subscribeCapability } from '../services/capabilities'

const fetchCard = fetchPublicCapability as jest.Mock
const subscribe = subscribeCapability as jest.Mock

function renderModal(name = 'listed-ok') {
  return render(
    <SubscribeModal
      open
      assetType="skill"
      assetName={name}
      onClose={() => undefined}
    />,
  )
}

beforeEach(() => {
  fetchCard.mockReset()
  subscribe.mockReset()
})

test('undeclared host list enables all four hosts', async () => {
  fetchCard.mockResolvedValueOnce({
    name: 'undeclared', hosts: ['grok', 'zcode', 'kimi', 'claude'], subscribable: true,
  })
  renderModal('undeclared')
  await waitFor(() => expect(screen.getByRole('radio', { name: /Grok/ })).not.toBeDisabled())
  expect(screen.getAllByRole('radio')).toHaveLength(4)
  expect(screen.getByRole('radio', { name: /ZCode/ })).not.toBeDisabled()
  expect(screen.getByRole('radio', { name: /Kimi/ })).not.toBeDisabled()
  expect(screen.getByRole('radio', { name: /Claude/ })).not.toBeDisabled()
  expect(document.body.textContent).not.toMatch(/礼包|安装此插件将获得|全部技能/)
  expect(subscribe).not.toHaveBeenCalled()
})

test('declared zero hosts still renders four disabled radios', async () => {
  fetchCard.mockResolvedValueOnce({
    name: 'zero', hosts: [], subscribable: true,
  })
  renderModal('zero')
  expect(await screen.findByText('该能力未声明支持任何宿主')).toBeInTheDocument()
  expect(screen.getAllByRole('radio')).toHaveLength(4)
  expect(screen.getByRole('radio', { name: /^Grok$/ })).toBeDisabled()
  expect(screen.getByRole('radio', { name: /^ZCode$/ })).toBeDisabled()
  expect(screen.getByRole('radio', { name: /^Kimi$/ })).toBeDisabled()
  expect(screen.getByRole('radio', { name: /^Claude$/ })).toBeDisabled()
  expect(subscribe).not.toHaveBeenCalled()
})

test('kimi-only disables grok with host note', async () => {
  fetchCard.mockResolvedValueOnce({
    name: 'kimi-only', hosts: ['kimi'], subscribable: true,
  })
  renderModal('kimi-only')
  expect(await screen.findByText('该能力未声明支持 Grok')).toBeInTheDocument()
  expect(screen.getAllByRole('radio')).toHaveLength(4)
  expect(screen.getByRole('radio', { name: /Grok/ })).toBeDisabled()
  expect(screen.getByRole('radio', { name: /Kimi/ })).not.toBeDisabled()
})

test('submit grok toasts subscribed and does not gift', async () => {
  fetchCard.mockResolvedValueOnce({
    name: 'listed-ok', hosts: ['grok', 'zcode', 'kimi', 'claude'], subscribable: true,
  })
  subscribe.mockResolvedValueOnce({ created: true, message: '已订阅到 Grok', host: 'grok', asset_id: 1 })
  const toast = jest.spyOn(message, 'success').mockImplementation(() => undefined as never)
  renderModal('listed-ok')
  await waitFor(() => expect(screen.getByRole('radio', { name: /Grok/ })).not.toBeDisabled())
  fireEvent.click(screen.getByRole('radio', { name: /Grok/ }))
  fireEvent.click(screen.getByRole('button', { name: /订阅到 Grok/ }))
  await waitFor(() => expect(subscribe).toHaveBeenCalledWith('skill', 'listed-ok', 'grok'))
  expect(subscribe).toHaveBeenCalledTimes(1)
  expect(toast).toHaveBeenCalledWith('已订阅到 Grok')
  toast.mockRestore()
})

test('idempotent success toasts frozen copy', async () => {
  fetchCard.mockResolvedValueOnce({
    name: 'listed-ok', hosts: ['grok', 'zcode', 'kimi', 'claude'], subscribable: true,
  })
  subscribe.mockResolvedValueOnce({
    created: false, already_subscribed: true, message: 'wrong', host: 'grok', asset_id: 1,
  })
  const toast = jest.spyOn(message, 'success').mockImplementation(() => undefined as never)
  renderModal('listed-ok')
  await waitFor(() => expect(screen.getByRole('radio', { name: /Grok/ })).not.toBeDisabled())
  fireEvent.click(screen.getByRole('radio', { name: /Grok/ }))
  fireEvent.click(screen.getByRole('button', { name: /订阅到 Grok/ }))
  await waitFor(() => expect(subscribe).toHaveBeenCalledTimes(1))
  expect(toast).toHaveBeenCalledWith('已订阅到 Grok，没有新增行。')
  toast.mockRestore()
})

test('MARKET_NOT_FOUND copy branches on code not message', async () => {
  fetchCard.mockRejectedValueOnce({
    response: { data: { code: 'MARKET_NOT_FOUND', message: '未找到该能力' } },
  })
  renderModal()
  expect(await screen.findByText('没有这个能力，不能订阅。')).toBeInTheDocument()
  expect(screen.queryByText('未找到该能力')).not.toBeInTheDocument()
})

test('MARKET_COMING_SOON copy branches on code not message', async () => {
  fetchCard.mockResolvedValueOnce({
    name: 'soon', hosts: ['grok', 'zcode', 'kimi', 'claude'], subscribable: false,
  })
  subscribe.mockRejectedValueOnce({
    response: { data: { code: 'MARKET_COMING_SOON', message: '预告项不可订阅' } },
  })
  renderModal('soon')
  await waitFor(() => expect(screen.getByRole('radio', { name: /Grok/ })).not.toBeDisabled())
  fireEvent.click(screen.getByRole('radio', { name: /Grok/ }))
  fireEvent.click(screen.getByRole('button', { name: /订阅到 Grok/ }))
  expect(await screen.findByText('这是预告项，现在不能订阅。')).toBeInTheDocument()
  expect(screen.queryByText('预告项不可订阅')).not.toBeInTheDocument()
})

test('hostNote distinguishes undeclared vs declared empty', () => {
  expect(hostNote('grok', [], true)).toBe('该能力未声明支持任何宿主')
  expect(hostNote('grok', ['kimi'], false)).toBe('该能力未声明支持 Grok')
})

test('frozen copy helpers match edge-states', () => {
  expect(COPY_BY_CODE.MARKET_NOT_FOUND).toBe('没有这个能力，不能订阅。')
  expect(COPY_BY_CODE.MARKET_COMING_SOON).toBe('这是预告项，现在不能订阅。')
  expect(successCopy('grok', true)).toBe('已订阅到 Grok')
  expect(successCopy('grok', false)).toBe('已订阅到 Grok，没有新增行。')
  expect(formErrorFromCode('MARKET_NOT_FOUND', '未找到该能力')).toBe('没有这个能力，不能订阅。')
  expect(formErrorFromCode('MARKET_COMING_SOON', '预告项不可订阅')).toBe('这是预告项，现在不能订阅。')
})
