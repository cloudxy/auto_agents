/**
 * 审计 F1-1：定价单一来源——价格读 /billing/plans，不手抄；读取失败降级「以结账页为准」。
 */
import React from 'react'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

jest.mock('../services/billing', () => ({ fetchPublicPlans: jest.fn() }))
jest.mock('../services/contact', () => ({ fetchPublicContact: jest.fn().mockRejectedValue(new Error('offline')) }))

import { fetchPublicPlans } from '../services/billing'
import { fetchPublicContact } from '../services/contact'
import Pricing from './Pricing'

const PLANS = [
  { id: 1, slug: 'free', name: '免费档', price_cents: 0, period: 'month', is_public: 1 },
  { id: 2, slug: 'pro', name: '专业档', price_cents: 39900, period: 'month', is_public: 1 },
  { id: 3, slug: 'enterprise', name: '企业档', price_cents: 1299000, period: 'year', is_public: 1 },
]

function renderPricing() {
  return render(<MemoryRouter><Pricing /></MemoryRouter>)
}

test('prices come from /billing/plans (no hand-copied ¥299)', async () => {
  ;(fetchPublicPlans as jest.Mock).mockResolvedValueOnce(PLANS)
  renderPricing()
  expect(await screen.findByText('¥399/月')).toBeInTheDocument()
  expect(screen.getByText('¥12,990/年')).toBeInTheDocument()
  expect(screen.getByText('¥0')).toBeInTheDocument()
  expect(document.body.textContent).not.toContain('¥299/月')
})

test('falls back to checkout price when plans fail to load', async () => {
  ;(fetchPublicPlans as jest.Mock).mockRejectedValueOnce(new Error('network'))
  renderPricing()
  expect(await screen.findAllByText('价格以结账页为准')).toHaveLength(2)
  expect(screen.getAllByRole('link', { name: '去结账' })).toHaveLength(1)  // 购买入口不受影响（企业档 D17 走联系我们）
})

test('home no longer says purchase is unavailable', () => {
  const fs = require('fs') as typeof import('fs')
  const path = require('path') as typeof import('path')
  const src = fs.readFileSync(path.join(__dirname, 'Home.tsx'), 'utf8')
  expect(src).not.toContain('尚未开通购买')
})

test('D17 / D25：企业档按需定制，联系我们带邮箱与响应时效；D32 撤下私有技能库', async () => {
  ;(fetchPublicPlans as jest.Mock).mockResolvedValueOnce([
    ...PLANS.filter((p: { slug: string }) => p.slug !== 'enterprise'),
    { id: 3, slug: 'enterprise', name: '企业档', price_cents: 99900, period: 'month', is_public: 1, sales_led: true },
  ])
  ;(fetchPublicContact as jest.Mock).mockResolvedValueOnce({
    duty_contact: '', contact_email: 'sales@example.com', contact_sla: '工作日 24 小时内回复',
  })
  renderPricing()
  expect(await screen.findByText('按需定制')).toBeInTheDocument()
  const contact = await screen.findByRole('link', { name: '联系我们' })
  expect(contact.getAttribute('href')).toBe(`mailto:sales@example.com?subject=${encodeURIComponent('企业档咨询')}`)
  expect(screen.getByText('sales@example.com · 工作日 24 小时内回复')).toBeInTheDocument()
  expect(document.body.textContent).not.toContain('¥999/月')
  expect(document.body.textContent).not.toContain('私有技能库')
})
