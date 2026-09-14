/**
 * T-03 企业注册：成功主按钮去后台登录；失败留在表单（GWT-04.1–04.4）。
 */
import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

jest.mock('../services/signup', () => ({
  tenantSignup: jest.fn(),
}))

jest.mock('../services/beacon', () => ({
  getAnonymousId: jest.fn(() => null),
}))

import { FREE_TIER_FEATURE_COPY } from '@auto-agents/frontend-shared'
import { tenantSignup } from '../services/signup'
import Register from './Register'

/** GWT Given 字面量。与 Pricing.test 同源独立 oracle，不从 DEFAULT_QUOTA 推导。 */
const GWT_01_1 = {
  concurrencyPhrase: '5 个并发任务',
  storagePhrase: '10,000 条结果存储',
  tokensPhrase: '20 万 LLM tokens/月',
} as const

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

const signup = tenantSignup as jest.Mock

function renderRegister() {
  return render(
    <MemoryRouter>
      <Register />
    </MemoryRouter>,
  )
}

function fillForm(opts?: { company?: string; email?: string; password?: string }) {
  fireEvent.change(screen.getByLabelText('企业名'), {
    target: { value: opts?.company ?? 'Acme Corp' },
  })
  fireEvent.change(screen.getByLabelText('管理员邮箱'), {
    target: { value: opts?.email ?? 'boss@acme.com' },
  })
  fireEvent.change(screen.getByLabelText('密码'), {
    target: { value: opts?.password ?? 'SuperSecret1!' },
  })
}

function submit() {
  fireEvent.click(screen.getByRole('button', { name: '创建企业' }))
}

beforeEach(() => {
  signup.mockReset()
  Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
})

test('GWT-04.1 success primary goes to admin login with from and named copy', async () => {
  signup.mockResolvedValue({
    tenant: { name: 'Acme Corp', slug: 'acme-corp' },
    owner: { username: 'boss', email: 'boss@acme.com' },
  })
  renderRegister()
  fillForm()
  submit()

  expect(await screen.findByText(
    '企业「Acme Corp」已开通，负责人 boss@acme.com。登录时请填写注册邮箱，登录后开始采集。',
  )).toBeInTheDocument()
  expect(document.body.textContent || '').not.toContain('企业「」')
  const login = screen.getByRole('link', { name: '登录管理后台' })
  const href = login.getAttribute('href') || ''
  expect(href).toContain('/login?from=')
  expect(decodeURIComponent(href)).toContain('/dashboard')
  expect(href).toMatch(/\/login\?from=/)
  expect(href).not.toContain('/register')
  expect(screen.getByRole('button', { name: '再注册一家' })).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: '再注册一家' })).not.toBeInTheDocument()
})

test('GWT-83.3 success screen names the registered email as the login identifier', async () => {
  signup.mockResolvedValue({
    tenant: { name: 'Acme Corp', slug: 'acme-corp' },
    owner: { username: 'boss', email: 'boss@acme.com' },
  })
  renderRegister()
  fillForm()
  submit()

  const copy = await screen.findByText(/已开通/)
  // 写明「登录时请填写注册邮箱」；负责人标识展示注册邮箱本身
  expect(copy).toHaveTextContent('登录时请填写注册邮箱')
  expect(copy).toHaveTextContent('boss@acme.com')
})

test('GWT-83.3 fallback without email still tells email login, never short-name-only', async () => {
  signup.mockResolvedValue({
    tenant: { name: 'Acme Corp', slug: 'acme-corp' },
    owner: { username: 'boss' },
  })
  renderRegister()
  fillForm()
  submit()

  const copy = await screen.findByText(/已开通/)
  expect(copy).toHaveTextContent('登录时请填写注册邮箱')
  // 展示短登录名不暗示「只能用短登录名」：提示句在场即合规（GWT-83.3 后半）
  expect(copy).toHaveTextContent('负责人 boss。')
})

test('GWT-04.2 failed register stays on form with 注册未完成 and no success screen', async () => {
  signup.mockRejectedValue({
    response: {
      status: 422,
      data: { success: false, code: 'VALIDATION_ERROR', message: '密码至少 8 位', data: { field: 'admin_password' } },
    },
  })
  renderRegister()
  fillForm({ password: 'shortpass' })
  submit()

  expect(await screen.findByRole('alert')).toHaveTextContent(/注册未完成/)
  expect(screen.getByText(/改正后再次创建企业/)).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: '登录管理后台' })).not.toBeInTheDocument()
  expect(screen.queryByText(/已开通/)).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: '创建企业' })).toBeInTheDocument()
  expect((screen.getByLabelText('企业名') as HTMLInputElement).value).toBe('Acme Corp')
})

test('GWT-04.3 secondary is 再注册一家; success primary is not 再注册', async () => {
  signup.mockResolvedValue({
    tenant: { name: 'Acme Corp', slug: 'acme-corp' },
    owner: { username: 'boss' },
  })
  renderRegister()
  fillForm()
  submit()
  await screen.findByRole('link', { name: '登录管理后台' })
  fireEvent.click(screen.getByRole('button', { name: '再注册一家' }))
  expect(screen.getByRole('button', { name: '创建企业' })).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: '登录管理后台' })).not.toBeInTheDocument()
})

test('GWT-04.4 occupancy failure is generic and does not leak other tenants', async () => {
  signup.mockRejectedValue({
    response: {
      status: 422,
      data: {
        success: false,
        code: 'SIGNUP_INCOMPLETE',
        message: '注册未完成，请检查填写内容',
        data: null,
      },
    },
  })
  renderRegister()
  fillForm({ company: 'Hijack Co', email: 'viewer@victim.test' })
  submit()

  expect(await screen.findByRole('alert')).toHaveTextContent('注册未完成，请检查填写内容')
  const copy = document.body.textContent || ''
  expect(copy).not.toMatch(/已注册/)
  expect(copy).not.toMatch(/加入企业/)
  expect(copy).not.toMatch(/Victim Co/)
  expect(copy).not.toMatch(/企业「」/)
  expect(screen.queryByRole('link', { name: '登录管理后台' })).not.toBeInTheDocument()
})

test('empty tenant or owner names never render empty book-title marks', async () => {
  signup.mockResolvedValue({
    tenant: { name: '  ', slug: 'blank' },
    owner: { username: '' },
  })
  renderRegister()
  fillForm()
  submit()
  expect(await screen.findByRole('alert')).toHaveTextContent(/注册未完成/)
  expect(document.body.textContent || '').not.toContain('企业「」')
  expect(screen.queryByRole('link', { name: '登录管理后台' })).not.toBeInTheDocument()
})

test('offline submit keeps form and shows network copy', async () => {
  Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
  renderRegister()
  fillForm()
  submit()
  expect(await screen.findByRole('alert')).toHaveTextContent('创建企业失败：网络不可用。检查连接后重试。')
  expect(signup).not.toHaveBeenCalled()
  expect(screen.getByRole('button', { name: '创建企业' })).toBeInTheDocument()
})

test('Register free-tier copy uses FREE_TIER_FEATURE_COPY (GWT Given 5 / 10,000 / 20 万)', () => {
  expect(FREE_TIER_FEATURE_COPY.task_concurrency).toBe(GWT_01_1.concurrencyPhrase)
  expect(FREE_TIER_FEATURE_COPY.result_storage).toBe(GWT_01_1.storagePhrase)
  expect(FREE_TIER_FEATURE_COPY.llm_tokens_month).toBe(GWT_01_1.tokensPhrase)
  renderRegister()
  const copy = document.body.textContent || ''
  expect(copy).toContain(GWT_01_1.concurrencyPhrase)
  expect(copy).toContain(GWT_01_1.storagePhrase)
  expect(copy).toContain(GWT_01_1.tokensPhrase)
  expect(copy).toContain('5')
  expect(copy).toContain('10,000')
  expect(copy).toContain('20 万')
  expect(copy).not.toContain('10000')
})

test('NFR-07 Register primary submit has 44px touch target', () => {
  renderRegister()
  assertTouchTarget(screen.getByRole('button', { name: '创建企业' }))
})

test('success unwraps once (no nested .data empty names)', async () => {
  signup.mockResolvedValue({
    tenant: { name: 'Acme Corp', slug: 'acme-corp' },
    owner: { username: 'boss' },
  })
  renderRegister()
  fillForm()
  submit()
  await screen.findByText(/企业「Acme Corp」/)
  expect(screen.queryByText(/企业「undefined」/)).not.toBeInTheDocument()
  await waitFor(() => expect(signup).toHaveBeenCalledTimes(1))
})

test('GWT-M51.1 primary is 创建企业 and success is company admin, not personal space', async () => {
  signup.mockResolvedValue({
    tenant: { name: 'Acme Corp', slug: 'acme-corp' },
    owner: { username: 'boss', email: 'boss@acme.com' },
  })
  renderRegister()
  expect(screen.getByRole('button', { name: '创建企业' })).toBeInTheDocument()
  expect(document.body.textContent || '').not.toMatch(/个人空间/)
  expect(document.body.textContent || '').not.toMatch(/去掉企业/)
  fillForm()
  submit()
  const login = await screen.findByRole('link', { name: '登录管理后台' })
  expect(decodeURIComponent(login.getAttribute('href') || '')).toContain('/dashboard')
  expect(decodeURIComponent(login.getAttribute('href') || '')).not.toMatch(/personal|me\/home|个人/)
  expect(document.body.textContent || '').not.toMatch(/个人空间/)
  expect(document.body.textContent || '').not.toContain('当前可买')
})

test('GWT-M51.2 empty company name: 请填写企业名, does not create', async () => {
  renderRegister()
  fillForm({ company: '' })
  submit()
  expect(await screen.findByText('请填写企业名')).toBeInTheDocument()
  expect(signup).not.toHaveBeenCalled()
  expect(screen.queryByRole('link', { name: '登录管理后台' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: '创建企业' })).toBeInTheDocument()
})

test('GWT-M51.4 company name of 1 char: 企业名至少 2 个字符, does not create', async () => {
  renderRegister()
  fillForm({ company: '甲' })
  submit()
  expect(await screen.findByText('企业名至少 2 个字符')).toBeInTheDocument()
  expect(signup).not.toHaveBeenCalled()
  expect(screen.queryByRole('link', { name: '登录管理后台' })).not.toBeInTheDocument()
})

test('GWT-M51.3 no personal-space CTA on the register form', () => {
  renderRegister()
  const copy = document.body.textContent || ''
  expect(copy).not.toMatch(/开通个人空间/)
  expect(copy).not.toMatch(/去掉企业只用个人账号/)
  expect(copy).not.toMatch(/个人空间/)
})

