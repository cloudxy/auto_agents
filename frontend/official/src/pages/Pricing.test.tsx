/**
 * T-21 定价：免费档 → /register；专业/企业「去结账」进 checkout?product=。
 */
import React from 'react'
import { render, screen } from '@testing-library/react'
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
const ENTERPRISE_ITEMS = ['工单支持', '中转站渠道组分配', '私有技能库', '专属客户成功'] as const

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
  screen.getAllByRole('link', { name: '去结账' }).forEach(assertTouchTarget)
})

test('GWT-U35.1/5 paid-tier 去结账 goes to checkout not register', () => {
  renderPricing()
  const paid = screen.getAllByRole('link', { name: '去结账' })
  expect(paid).toHaveLength(2)
  expect(paid[0]).toHaveAttribute('href', 'http://localhost:9112/billing/checkout?product=plan_pro')
  expect(paid[1]).toHaveAttribute('href', 'http://localhost:9112/billing/checkout?product=plan_enterprise')
  paid.forEach((link) => {
    const href = link.getAttribute('href') || ''
    expect(href).not.toContain('/register')
    expect(href).not.toMatch(/[?&]product=plan_ent(?:&|$)/)
  })
  const copy = document.body.textContent || ''
  expect(copy).not.toContain('预告不可购买')
  expect(copy).not.toContain('尚未开通购买')
  expect(copy).not.toContain('当前可买')
  expect(copy).not.toContain('联系升级')
  expect(screen.queryByRole('link', { name: '联系平台' })).toBeNull()
})

test('closed-set B items are listed without 预告 tag', () => {
  renderPricing()
  const copy = document.body.textContent || ''
  expect(FREE_TIER_FEATURE_COPY.task_concurrency).toBe(GWT_01_1.concurrencyPhrase)
  expect(FREE_TIER_FEATURE_COPY.result_storage).toBe(GWT_01_1.storagePhrase)
  expect(FREE_TIER_FEATURE_COPY.llm_tokens_month).toBe(GWT_01_1.tokensPhrase)
  expect(copy).toContain(GWT_01_1.concurrencyPhrase)
  expect(copy).toContain(GWT_01_1.storagePhrase)
  expect(copy).toContain(GWT_01_1.tokensPhrase)
  expect(copy).toContain('工单支持')
  expect(copy).toContain('中转站渠道组分配')
  expect(copy).toContain('私有技能库')
  expect(copy).toContain('专属客户成功')
  expect(screen.queryAllByText('预告')).toHaveLength(0)
  ENTERPRISE_ITEMS.forEach((label) => {
    expect(featureRow(label).textContent || '').not.toContain('预告')
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

test('test_no_currently_buyable_relay_copy_gwt_60_9', () => {
  renderPricing()
  const copy = document.body.textContent || ''
  expect(copy).not.toContain('当前可买')
  expect(copy).not.toContain('可买中转')
  expect(copy).not.toContain('开通即送中转')
  const relayRow = featureRow('中转站渠道组分配')
  expect(relayRow.textContent || '').toContain('中转站渠道组分配')
})

test('pricing source has no session branch (GWT-01.3)', () => {
  const fs = require('fs') as typeof import('fs')
  const path = require('path') as typeof import('path')
  const src = fs.readFileSync(path.join(__dirname, 'Pricing.tsx'), 'utf8')
  expect(src).not.toMatch(/useAuthStore|isAuthenticated|sessionStorage/)
  renderPricing()
  expect(screen.getByRole('link', { name: /免费注册/ })).toBeInTheDocument()
  expect(screen.getAllByRole('link', { name: '去结账' })).toHaveLength(2)
})
