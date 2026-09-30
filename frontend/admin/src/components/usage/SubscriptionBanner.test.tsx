/**
 * 决策 D22：用量页展示当前套餐与到期状态——到期前 7 天提示续费，宽限期内明确告知何时转免费档
 */
import React from 'react'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { withQuery } from '../../testUtils'
import SubscriptionBanner from './SubscriptionBanner'
import { fetchSubscription } from '../../services/billing'

jest.mock('../../services/billing', () => ({ fetchSubscription: jest.fn() }))

const DAY = 86400000
const iso = (offsetDays: number) => new Date(Date.now() + offsetDays * DAY).toISOString()
const sub = (over: Record<string, unknown>) => ({
  id: 1, plan_id: 2, status: 'active', tenant_id: 1, plan_slug: 'pro', plan_name: '专业档',
  current_period_end: iso(20), grace_until: iso(23), in_grace: false, ...over,
})
const renderBanner = (canRenew = true) =>
  render(withQuery(<MemoryRouter><SubscriptionBanner canRenew={canRenew} /></MemoryRouter>))

test('正常有效期：显示套餐与到期日，不催续费', async () => {
  ;(fetchSubscription as jest.Mock).mockResolvedValue(sub({}))
  renderBanner()
  expect(await screen.findByText(/当前套餐：专业档/)).toBeInTheDocument()
  expect(screen.getByText(/有效期至/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /续\s*费/ })).toBeNull()
})

test('7 天内到期：提示续费并给出入口', async () => {
  ;(fetchSubscription as jest.Mock).mockResolvedValue(sub({ current_period_end: iso(3), grace_until: iso(6) }))
  renderBanner()
  expect(await screen.findByText(/即将到期/)).toBeInTheDocument()
  expect(screen.getByText(/从原到期日顺延/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /去\s*续\s*费/ })).toBeInTheDocument()
})

test('宽限期：告知何时转为免费档、数据保留', async () => {
  ;(fetchSubscription as jest.Mock).mockResolvedValue(sub({ current_period_end: iso(-1), grace_until: iso(2), in_grace: true }))
  renderBanner()
  expect(await screen.findByText(/已到期/)).toBeInTheDocument()
  expect(screen.getByText(/起转为免费档/)).toBeInTheDocument()
  expect(screen.getByText(/数据全部保留/)).toBeInTheDocument()
})

test('免费档：只显示当前套餐；只读成员看不到续费入口', async () => {
  ;(fetchSubscription as jest.Mock).mockResolvedValue(sub({ plan_slug: 'free', plan_name: '免费档', current_period_end: null, grace_until: null }))
  renderBanner(false)
  expect(await screen.findByText(/当前套餐：免费档/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /续\s*费/ })).toBeNull()
})
