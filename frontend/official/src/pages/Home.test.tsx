/**
 * T-01 官网首页诚实面 + T-06 FR-U04：Hero 第一句锁采集；支付/中转不得顶替。
 */
import React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

jest.mock('../services/skills', () => ({
  listPublicSkills: jest.fn(),
  getPublicSkill: jest.fn(),
}))

import { listPublicSkills } from '../services/skills'
import Home, { HERO_FIRST_SENTENCE } from './Home'

const mockedList = listPublicSkills as jest.MockedFunction<typeof listPublicSkills>

const FORBIDDEN_GATEWAY = '直连平台网关'
const FORBIDDEN_RELAY_TOKEN = '我的中转令牌'
const FORBIDDEN_CLAIMS = ['抽取准确率', '已校准', '官方认证', '正品保证'] as const

const FORBIDDEN_HERO = ['订阅成功', '支付成功', '中转可买', '当前可买'] as const
const PAYMENT_REPLACE = ['去结账', '支付宝', '微信支付', '订阅成功', '支付成功', '中转可买'] as const

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

beforeEach(() => {
  mockedList.mockReset()
  mockedList.mockRejectedValue(new Error('public list unavailable'))
})

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

test('GWT-U04.1 hero first sentence is collection paste-link / 出数', () => {
  expect(HERO_FIRST_SENTENCE).toContain('粘贴链接')
  expect(HERO_FIRST_SENTENCE).toContain('出数')
  FORBIDDEN_HERO.forEach((phrase) => expect(HERO_FIRST_SENTENCE).not.toContain(phrase))

  renderHome()
  const first = screen.getByTestId('hero-first-sentence')
  const text = (first.textContent || '').trim()
  expect(text.startsWith(HERO_FIRST_SENTENCE)).toBe(true)
  const hero = screen.getByTestId('hero-section')
  const heroCopy = hero.textContent || ''
  FORBIDDEN_HERO.forEach((phrase) => expect(heroCopy).not.toContain(phrase))
  expect(heroCopy).not.toContain('去结账')
})

test('GWT-U04.2 featured empty does not replace hero with payment or subscribe', async () => {
  mockedList.mockResolvedValue({ total: 0, items: [] })
  renderHome()
  const first = screen.getByTestId('hero-first-sentence')
  expect((first.textContent || '').trim().startsWith(HERO_FIRST_SENTENCE)).toBe(true)

  const empty = await screen.findByTestId('featured-empty')
  expect(empty).toHaveTextContent('还没有上架的能力')
  const emptyCopy = empty.textContent || ''
  PAYMENT_REPLACE.forEach((phrase) => expect(emptyCopy).not.toContain(phrase))
  expect(screen.queryByTestId('featured-error')).not.toBeInTheDocument()
  expect(screen.queryByText('暂时无法加载能力')).not.toBeInTheDocument()
})

test('GWT-U04.3 no edit-hero entry on official home', () => {
  const fs = require('fs') as typeof import('fs')
  const path = require('path') as typeof import('path')
  const homeSrc = fs.readFileSync(path.join(__dirname, 'Home.tsx'), 'utf8')
  const appSrc = fs.readFileSync(path.join(__dirname, '../App.tsx'), 'utf8')
  const layoutSrc = fs.readFileSync(
    path.join(__dirname, '../components/layout/SiteLayout.tsx'),
    'utf8',
  )
  expect(homeSrc).not.toMatch(/\/billing|payment_succeeded|relay\/groups/)
  ;[homeSrc, appSrc, layoutSrc].forEach((src: string) => {
    expect(src).not.toMatch(/编辑官网第一句|改 Hero|heroEditor/)
  })

  renderHome()
  const copy = document.body.textContent || ''
  expect(copy).not.toContain('编辑官网第一句')
  expect(copy).not.toContain('改 Hero')
  expect(screen.queryByRole('button', { name: /编辑官网第一句|改 Hero/ })).not.toBeInTheDocument()
  expect(screen.queryByRole('link', { name: /编辑官网第一句|改 Hero/ })).not.toBeInTheDocument()
})

test('GWT-U24.1 homepage visitor copy has no 当前可买', async () => {
  renderHome()
  expect(await screen.findByText('暂时无法加载能力')).toBeInTheDocument()
  const copy = document.body.textContent || ''
  expect(copy).not.toContain('当前可买')
})

