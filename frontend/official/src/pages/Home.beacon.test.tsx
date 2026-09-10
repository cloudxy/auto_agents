/**
 * T-12 首页旁路 CTA：进入管理后台 / 体验 AI 流程不进五档 cta。
 */
import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

jest.mock('../services/skills', () => ({
  listPublicSkills: jest.fn().mockRejectedValue(new Error('skip')),
  getPublicSkill: jest.fn(),
}))

jest.mock('../services/beacon', () => ({
  trackCta: jest.fn(),
  trackPageView: jest.fn(),
  getAnonymousId: jest.fn(),
  ensureAnonymousId: jest.fn(),
}))

import { trackCta } from '../services/beacon'
import Home from './Home'

const FUNNEL = ['register_free', 'pricing_pro', 'pricing_enterprise', 'login', 'browse_market']

function renderHome() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

test('homepage enter-admin bypass is not a funnel cta (GWT-15.7)', () => {
  renderHome()
  fireEvent.click(screen.getByRole('link', { name: '登录管理后台' }))
  expect(trackCta).toHaveBeenCalledWith('enter_admin')
  expect(FUNNEL).not.toContain('enter_admin')
})

test('homepage try-ai-flow bypass is not a funnel cta (GWT-15.19)', () => {
  renderHome()
  fireEvent.click(screen.getByRole('button', { name: '体验 AI 采集流程' }))
  expect(trackCta).toHaveBeenCalledWith('try_ai_flow')
  expect(FUNNEL).not.toContain('try_ai_flow')
})
