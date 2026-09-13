/**
 * T-11 FR-U13：商店详情不可信正文纯文本（GWT-U13.1/2/3）。
 * 出处不泄漏未上架父插件仍钉在本页（GWT-32.5）。
 */
import React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import type { PublicAssetDetail } from '../services/capabilities'

jest.mock('../services/capabilities', () => ({
  getPublicAsset: jest.fn(),
}))

import { getPublicAsset } from '../services/capabilities'
import CapabilityDetail from './CapabilityDetail'

const fetchDetail = getPublicAsset as jest.MockedFunction<typeof getPublicAsset>

export const XSS_PAYLOAD = '<script>alert(1)</script> <img src=x onerror=alert(1)>'

const listedSkill = (over: Partial<PublicAssetDetail> = {}): PublicAssetDetail => ({
  asset_type: 'skill',
  name: 'child-skill',
  title: '子卡',
  description: '说明',
  category: 'dev-tools',
  listing_state: 'listed',
  subscribable: true,
  license: 'MIT',
  source_author: '署名甲',
  source_url: 'https://example.invalid/src',
  hosts: ['grok', 'zcode', 'kimi', 'claude'],
  includes: [],
  skill_md: XSS_PAYLOAD,
  origin: { name: 'secret-parent', title: '署名甲', asset_type: 'plugin' },
  ...over,
})

function renderDetail(path: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/capabilities/:type/:slug" element={<CapabilityDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const ORIG_ADMIN_URL = process.env.REACT_APP_ADMIN_URL

beforeEach(() => {
  fetchDetail.mockReset()
  Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
  process.env.REACT_APP_ADMIN_URL = 'https://admin.example.test'
})

afterEach(() => {
  if (ORIG_ADMIN_URL === undefined) delete process.env.REACT_APP_ADMIN_URL
  else process.env.REACT_APP_ADMIN_URL = ORIG_ADMIN_URL
})

test('GWT-U13.1 skill body is text: <script>alert(1)</script> visible, no script/img from body', async () => {
  const alertSpy = jest.spyOn(window, 'alert').mockImplementation(() => {})
  fetchDetail.mockResolvedValue(listedSkill())
  const { container } = renderDetail('/capabilities/skill/child-skill')
  const body = await screen.findByTestId('skill-md')
  expect(body.textContent).toContain('<script>alert(1)</script>')
  expect(body.textContent).toContain('<img src=x onerror=alert(1)>')
  expect(body.innerHTML).toContain('&lt;script&gt;')
  expect(body.querySelector('script')).toBeNull()
  expect(body.querySelector('img')).toBeNull()
  expect(container.querySelector('script')).toBeNull()
  expect(container.querySelector('img[src="x"]')).toBeNull()
  expect(container.querySelector('img[onerror]')).toBeNull()
  expect(alertSpy).not.toHaveBeenCalled()
  expect(document.body.textContent || '').not.toContain('当前可买')
  alertSpy.mockRestore()
})

test('GWT-U13.2 empty skill_md shows 暂无说明 and does not execute script', async () => {
  fetchDetail.mockResolvedValue(listedSkill({ skill_md: '', body_md: '' }))
  const { container } = renderDetail('/capabilities/skill/child-skill')
  expect(await screen.findByTestId('skill-md-empty')).toHaveTextContent('暂无说明')
  expect(screen.queryByTestId('skill-md')).not.toBeInTheDocument()
  expect(container.querySelector('script')).toBeNull()
  expect(container.querySelector('img[src="x"]')).toBeNull()
})

test('GWT-32.5 unlisted parent origin is plain text, not a store link', async () => {
  fetchDetail.mockResolvedValue(listedSkill())
  const { container } = renderDetail('/capabilities/skill/child-skill')
  const origin = await screen.findByTestId('origin')
  expect(origin.textContent).toContain('署名甲')
  expect(origin.querySelector('a')).toBeNull()
  expect(container.querySelector('a[href="/capabilities/plugin/secret-parent"]')).toBeNull()
  expect(container.querySelector('a[href*="secret-parent"]')).toBeNull()
})

test('listed parent origin renders a store link when href is present', async () => {
  fetchDetail.mockResolvedValue(listedSkill({
    origin: {
      name: 'pub-parent',
      title: '已上架父插件',
      asset_type: 'plugin',
      href: '/capabilities/plugin/pub-parent',
    },
  }))
  renderDetail('/capabilities/skill/child-skill')
  const origin = await screen.findByTestId('origin')
  expect(origin.querySelector('a')).toHaveAttribute('href', '/capabilities/plugin/pub-parent')
  expect(origin.textContent).toContain('已上架父插件')
})

test('GWT-U13.3 unlisted GET is store-missing copy, body not rendered, no script', async () => {
  fetchDetail.mockRejectedValue({
    response: { status: 404, data: `<html><body>${XSS_PAYLOAD}</body></html>` },
  })
  const { container } = renderDetail('/capabilities/plugin/unlisted-x')
  expect(await screen.findByText('页面不存在，可能已被移除或地址有误')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '返回首页' })).toBeInTheDocument()
  expect(screen.queryByText('已下架')).not.toBeInTheDocument()
  expect(screen.queryByText('能力详情加载失败。检查网络后重试。')).not.toBeInTheDocument()
  expect(screen.queryByTestId('skill-md')).not.toBeInTheDocument()
  expect(screen.queryByTestId('skill-md-empty')).not.toBeInTheDocument()
  expect(container.querySelector('script')).toBeNull()
  expect(container.querySelector('img[src="x"]')).toBeNull()
})

test('load failure shows retry copy, not empty success', async () => {
  fetchDetail.mockRejectedValue(new Error('network down'))
  renderDetail('/capabilities/skill/child-skill')
  expect(await screen.findByText('能力详情加载失败。检查网络后重试。')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument()
})

test('offline failure uses offline copy', async () => {
  Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
  fetchDetail.mockRejectedValue(new Error('offline'))
  renderDetail('/capabilities/skill/child-skill')
  expect(await screen.findByText('打不开这份说明：网络不可用。连接恢复后重试。')).toBeInTheDocument()
})

test('GWT-U11.2 closed detail is 能力市场未开放, body not rendered', async () => {
  fetchDetail.mockResolvedValue(listedSkill({
    market_closed: true,
    message: '能力市场未开放',
    subscribable: false,
    skill_md: XSS_PAYLOAD,
  }))
  renderDetail('/capabilities/skill/u112-skill')
  expect(await screen.findByText('能力市场未开放')).toBeInTheDocument()
  expect(screen.getByText('开放后，已上架的能力会出现在这里。')).toBeInTheDocument()
  expect(screen.queryByTestId('skill-md')).not.toBeInTheDocument()
  expect(screen.queryByRole('link', { name: '登录后订阅' })).not.toBeInTheDocument()
  expect(document.body.textContent || '').not.toContain(XSS_PAYLOAD)
  expect(document.body.textContent || '').not.toContain('当前可买')
})

test('coming_soon has preview mark, no subscribe, no gift-pack or enable-host copy', async () => {
  fetchDetail.mockResolvedValue(listedSkill({
    listing_state: 'coming_soon',
    subscribable: false,
    skill_md: '预告正文',
  }))
  renderDetail('/capabilities/skill/child-skill')
  expect(await screen.findByText('预告')).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: '登录后订阅' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /订阅/ })).not.toBeInTheDocument()
  const copy = document.body.textContent || ''
  expect(copy).not.toContain('尚未上架')
  expect(copy).not.toContain('安装此插件将获得全部技能')
  expect(copy).not.toContain('启用到宿主')
  expect(copy).not.toContain('enable-host')
})

test('listed detail offers 登录后订阅 and no gift-pack copy', async () => {
  fetchDetail.mockResolvedValue(listedSkill())
  renderDetail('/capabilities/skill/child-skill')
  expect(await screen.findByRole('link', { name: '登录后订阅' })).toBeInTheDocument()
  const copy = document.body.textContent || ''
  expect(copy).not.toContain('安装此插件将获得全部技能')
  expect(copy).not.toContain('启用到宿主')
})

test('login-after-subscribe CTA href has subscribeType and subscribeName, not from=/capabilities/', async () => {
  process.env.REACT_APP_ADMIN_URL = 'https://admin.example.test'
  fetchDetail.mockResolvedValue(listedSkill())
  renderDetail('/capabilities/skill/child-skill')
  const cta = await screen.findByRole('link', { name: '登录后订阅' })
  const href = cta.getAttribute('href') || ''
  expect(href).toContain('subscribeType=skill')
  expect(href).toContain('subscribeName=child-skill')
  expect(href).not.toContain('from=/capabilities/')
  expect(href).toMatch(/^https:\/\/admin\.example\.test\/login\?/)
  expect(href).not.toContain('localhost:9112')
})

test('hides 登录后订阅 when REACT_APP_ADMIN_URL is unset', async () => {
  delete process.env.REACT_APP_ADMIN_URL
  fetchDetail.mockResolvedValue(listedSkill())
  renderDetail('/capabilities/skill/child-skill')
  expect(await screen.findByTestId('skill-md')).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: '登录后订阅' })).not.toBeInTheDocument()
})

test('GWT-39.1 command detail shows slash, body as text, subscribe, not plugin JSON', async () => {
  fetchDetail.mockResolvedValue({
    asset_type: 'command',
    name: 'pack__run-task',
    title: '跑任务',
    description: '独立命令卡',
    category: 'command',
    listing_state: 'listed',
    subscribable: true,
    slash: 'sdlc',
    body_md: XSS_PAYLOAD,
    hosts: ['grok', 'zcode', 'kimi', 'claude'],
    includes: [],
  })
  const { container } = renderDetail('/capabilities/command/pack__run-task')
  expect(await screen.findByRole('heading', { name: '跑任务' })).toBeInTheDocument()
  expect(screen.getByTestId('command-slash')).toHaveTextContent('/sdlc')
  const body = screen.getByTestId('skill-md')
  expect(body.textContent).toContain('<script>alert(1)</script>')
  expect(body.querySelector('script')).toBeNull()
  expect(body.querySelector('img')).toBeNull()
  expect(container.querySelector('script')).toBeNull()
  const cta = screen.getByRole('link', { name: '登录后订阅' })
  expect(cta.getAttribute('href') || '').toContain('subscribeType=command')
  expect(cta.getAttribute('href') || '').toContain('subscribeName=pack__run-task')
  const copy = document.body.textContent || ''
  expect(copy).not.toContain('plugin.json')
  expect(copy).not.toContain('安装此插件将获得全部技能')
  expect(copy).not.toContain('启用到宿主')
  expect(copy).not.toContain('市场分析')
  expect(copy).not.toContain('产品事实')
})
