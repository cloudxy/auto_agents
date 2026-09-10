/**
 * T-01 定价分档：免费档 → /register；付费档预告不可购买；GWT-70.4 文案。
 */
import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { FREE_TIER_FEATURE_COPY } from '@auto-agents/frontend-shared'

import Pricing from './Pricing'

/** GWT-01.1 Given 字面量。与 Usage.test 同源独立 oracle，不从 DEFAULT_QUOTA 推导。 */
const GWT_01_1 = {
  concurrencyPhrase: '5 个并发任务',
  storagePhrase: '10,000 条结果存储',
  tokensPhrase: '20 万 LLM tokens/月',
} as const

const FORBIDDEN_GATEWAY = '直连平台网关'
const FORBIDDEN_RELAY_TOKEN = '我的中转令牌'
const FORBIDDEN_CLAIMS = ['抽取准确率', '已校准', '官方认证', '正品保证'] as const
const PREVIEW_ITEMS = ['工单支持', '中转站渠道组分配', '私有技能库', '专属客户成功'] as const

function featureRow(label: string): HTMLElement {
  return screen.getByText((_, node) =>
    node?.tagName === 'P' && (node.textContent || '').includes(label),
  )
}

function renderPricing() {
  return render(
    <MemoryRouter>
      <Pricing />
    </MemoryRouter>,
  )
}

test('test_no_direct_gateway_or_relay_token_copy', () => {
  renderPricing()
  const copy = document.body.textContent || ''
  expect(copy).not.toContain(FORBIDDEN_GATEWAY)
  expect(copy).not.toContain(FORBIDDEN_RELAY_TOKEN)
  expect(screen.queryByRole('link', { name: FORBIDDEN_GATEWAY })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: FORBIDDEN_RELAY_TOKEN })).not.toBeInTheDocument()
})

function touchPx(value: string): number {
  if (!value) return 0
  if (value.includes('--size-touch')) return 44
  const n = Number.parseFloat(value)
  return Number.isFinite(n) ? n : 0
}

function assertTouchTarget(el: HTMLElement) {
  const computed = window.getComputedStyle(el)
  const minH = el.style.minHeight || computed.minHeight
  const minW = el.style.minWidth || computed.minWidth
  const height = el.style.height || computed.height
  const width = el.style.width || computed.width
  expect(Math.max(touchPx(minH), touchPx(height))).toBeGreaterThanOrEqual(44)
  expect(Math.max(touchPx(minW), touchPx(width))).toBeGreaterThanOrEqual(44)
}

test('free-tier primary CTA goes to register', () => {
  renderPricing()
  const free = screen.getByRole('link', { name: /免费注册/ })
  expect(free).toHaveAttribute('href', '/register')
})

test('NFR-07 Pricing primary CTAs have 44px touch target', () => {
  renderPricing()
  assertTouchTarget(screen.getByRole('link', { name: /免费注册/ }))
})

test('paid-tier primary CTA does not go to register', () => {
  renderPricing()
  const paid = screen.getAllByRole('button', { name: '预告不可购买' })
  expect(paid.length).toBe(2)
  paid.forEach((btn) => {
    expect(btn).not.toHaveAttribute('href', '/register')
    expect(btn.closest('a')).toBeNull()
  })

  fireEvent.click(paid[0])
  expect(screen.getByText('该档尚未开通购买。')).toBeInTheDocument()
  const contact = screen.getByRole('link', { name: '联系平台' })
  expect(contact.getAttribute('href') || '').toMatch(/^mailto:/)
  expect(contact.getAttribute('href') || '').not.toContain('/register')
  expect(document.body.textContent || '').not.toContain('现在就能买到并开通')
  expect(document.body.textContent || '').not.toContain('再开一家免费企业')
})

test('closed-set B items are preview not currently buyable', () => {
  renderPricing()
  const copy = document.body.textContent || ''
  expect(FREE_TIER_FEATURE_COPY.task_concurrency).toBe(GWT_01_1.concurrencyPhrase)
  expect(FREE_TIER_FEATURE_COPY.result_storage).toBe(GWT_01_1.storagePhrase)
  expect(FREE_TIER_FEATURE_COPY.llm_tokens_month).toBe(GWT_01_1.tokensPhrase)
  expect(copy).toContain(GWT_01_1.concurrencyPhrase)
  expect(copy).toContain(GWT_01_1.storagePhrase)
  expect(copy).toContain(GWT_01_1.tokensPhrase)
  ;([GWT_01_1.concurrencyPhrase, GWT_01_1.storagePhrase, GWT_01_1.tokensPhrase] as const).forEach((label) => {
    const row = screen.getByText((_, node) => {
      if (node?.tagName !== 'P') return false
      return (node.textContent || '').replace(/\s+/g, ' ').trim() === `✓ ${label}`
    })
    expect(row.textContent || '').not.toContain('预告')
  })
  expect(copy).toContain('工单支持')
  expect(copy).toContain('中转站渠道组分配')
  expect(copy).toContain('私有技能库')
  expect(copy).toContain('专属客户成功')
  expect(screen.getAllByText('预告').length).toBeGreaterThan(0)
  PREVIEW_ITEMS.forEach((label) => {
    expect(featureRow(label).textContent || '').toContain('预告')
  })
})

test('members and usage boards are current on free tier (GWT-01.10 copy)', () => {
  renderPricing()
  ;(['成员管理', '用量看板'] as const).forEach((label) => {
    const text = featureRow(label).textContent || ''
    expect(text).toContain(label)
    expect(text).not.toContain('预告')
  })
})

test('test_no_accuracy_or_certification_copy', () => {
  renderPricing()
  const copy = document.body.textContent || ''
  FORBIDDEN_CLAIMS.forEach((phrase) => expect(copy).not.toContain(phrase))
})

test('pricing source has no session branch (GWT-01.3)', () => {
  const fs = require('fs') as typeof import('fs')
  const path = require('path') as typeof import('path')
  const src = fs.readFileSync(path.join(__dirname, 'Pricing.tsx'), 'utf8')
  expect(src).not.toMatch(/useAuthStore|isAuthenticated|sessionStorage/)
  renderPricing()
  expect(screen.getByRole('link', { name: /免费注册/ })).toBeInTheDocument()
  expect(screen.getAllByRole('button', { name: '预告不可购买' })).toHaveLength(2)
})
