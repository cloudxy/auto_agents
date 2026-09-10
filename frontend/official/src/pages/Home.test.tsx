/**
 * T-01 官网首页诚实面：无虚构规模；精选失败非空成功句；GWT-70.4 文案。
 */
import React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

jest.mock('../services/skills', () => ({
  listPublicSkills: jest.fn().mockRejectedValue(new Error('public list unavailable')),
  getPublicSkill: jest.fn(),
}))

import Home from './Home'

const FORBIDDEN_GATEWAY = '直连平台网关'
const FORBIDDEN_RELAY_TOKEN = '我的中转令牌'
const FORBIDDEN_CLAIMS = ['抽取准确率', '已校准', '官方认证', '正品保证'] as const

function renderHome() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

test('test_no_direct_gateway_or_relay_token_copy', async () => {
  renderHome()
  expect(await screen.findByText('暂时无法加载能力')).toBeInTheDocument()
  const copy = document.body.textContent || ''
  expect(copy).not.toContain(FORBIDDEN_GATEWAY)
  expect(copy).not.toContain(FORBIDDEN_RELAY_TOKEN)
  expect(screen.queryByRole('link', { name: FORBIDDEN_GATEWAY })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: FORBIDDEN_RELAY_TOKEN })).not.toBeInTheDocument()
})

test('hero has no placeholder scale stats', () => {
  renderHome()
  const copy = document.body.textContent || ''
  expect(copy).not.toContain('128,000+')
  expect(copy).not.toContain('12 节点')
  expect(copy).not.toContain('3.2 亿条')
  expect(copy).not.toContain('示意数据')
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
  renderHome()
  const links = screen.getAllByRole('link', { name: /免费注册/ })
  expect(links.length).toBeGreaterThan(0)
  links.forEach((el) => expect(el).toHaveAttribute('href', '/register'))
})

test('NFR-07 Home primary CTAs have 44px touch target', () => {
  renderHome()
  const links = screen.getAllByRole('link', { name: /免费注册/ })
  expect(links.length).toBeGreaterThan(0)
  links.forEach((el) => assertTouchTarget(el))
})

test('featured list failure shows retry not empty-success copy', async () => {
  renderHome()
  expect(await screen.findByText('暂时无法加载能力')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /重试/ })).toBeInTheDocument()
  expect(screen.queryByText(/还没有技能/)).not.toBeInTheDocument()
  expect(screen.queryByText(/暂无已发布/)).not.toBeInTheDocument()
})

test('paste-link task result sell is current not 预告 (GWT-01.8)', async () => {
  renderHome()
  expect(await screen.findByText('暂时无法加载能力')).toBeInTheDocument()
  const copy = document.body.textContent || ''
  expect(copy).toContain('粘贴链接')
  expect(copy).toContain('提交任务')
  expect(copy).toContain('查看结果')
  expect(copy).not.toMatch(/粘贴链接[\s\S]{0,40}预告/)
  expect(copy).not.toMatch(/预告[\s\S]{0,40}粘贴链接/)
})

test('test_no_accuracy_or_certification_copy', async () => {
  renderHome()
  expect(await screen.findByText('暂时无法加载能力')).toBeInTheDocument()
  const copy = document.body.textContent || ''
  FORBIDDEN_CLAIMS.forEach((phrase) => expect(copy).not.toContain(phrase))
})

test('home page source has no session branch (GWT-01.3)', () => {
  const fs = require('fs') as typeof import('fs')
  const path = require('path') as typeof import('path')
  const src = fs.readFileSync(path.join(__dirname, 'Home.tsx'), 'utf8')
  expect(src).not.toMatch(/useAuthStore|isAuthenticated|sessionStorage/)
})
