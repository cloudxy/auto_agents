/**
 * T-23 / FR-U24 机械钉：访客可见面源码与渲染不得出现 FR-U24 四字。
 * 不实现支付通知。Hero 仍锁采集（T-06）。
 */
import fs from 'fs'
import path from 'path'
import React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

jest.mock('./services/skills', () => ({
  listPublicSkills: jest.fn().mockRejectedValue(new Error('public list unavailable')),
  getPublicSkill: jest.fn(),
}))

jest.mock('./services/capabilities', () => ({
  listPublicAssets: jest.fn(),
}))

import { listPublicAssets } from './services/capabilities'
import Home, { HERO_FIRST_SENTENCE } from './pages/Home'
import Pricing from './pages/Pricing'
import Capabilities from './pages/Capabilities'

const NEEDLE = '当前可买'
const SRC_ROOT = __dirname
const SHARED_SRC = path.join(__dirname, '../../shared/src')
const SURFACES = [
  'pages/Home.tsx',
  'pages/Pricing.tsx',
  'pages/Capabilities.tsx',
  'components/home/FeaturesSection.tsx',
  'components/layout/SiteLayout.tsx',
] as const

function skipName(name: string): boolean {
  if (name === 'node_modules' || name === '__mocks__' || name === 'dist') return true
  return /\.(test|spec)\.[jt]sx?$/.test(name)
}

function walkTs(dir: string): string[] {
  const out: string[] = []
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    if (skipName(ent.name)) continue
    const full = path.join(dir, ent.name)
    if (ent.isDirectory()) {
      out.push(...walkTs(full))
      continue
    }
    if (/\.[jt]sx?$/.test(ent.name) && !ent.name.endsWith('.d.ts')) out.push(full)
  }
  return out
}

function filesWithNeedle(root: string): string[] {
  return walkTs(root).filter((file) => fs.readFileSync(file, 'utf8').includes(NEEDLE))
}

function wrap(ui: React.ReactElement, url: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path="/" element={ui} />
          <Route path="/pricing" element={ui} />
          <Route path="/capabilities" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  ;(listPublicAssets as jest.Mock).mockReset()
  ;(listPublicAssets as jest.Mock).mockResolvedValue({
    items: [], total: 0, market_closed: false, message: '暂无已上架能力',
  })
})

test('GWT-U24 mechanical nail: homepage/pricing/capabilities source+render have no 当前可买', async () => {
  expect(filesWithNeedle(SRC_ROOT)).toEqual([])
  expect(filesWithNeedle(SHARED_SRC)).toEqual([])
  SURFACES.forEach((rel) => {
    const full = path.join(SRC_ROOT, rel)
    expect(fs.existsSync(full)).toBe(true)
    const src = fs.readFileSync(full, 'utf8')
    expect(src).not.toContain(NEEDLE)
  })
  const pricingSrc = fs.readFileSync(path.join(SRC_ROOT, 'pages/Pricing.tsx'), 'utf8')
  expect(pricingSrc).not.toMatch(/payment_succeeded|\/billing\/notify/)
  expect(HERO_FIRST_SENTENCE).toBe('粘贴链接即可出数。')

  wrap(<Home />, '/')
  expect(await screen.findByTestId('hero-first-sentence')).toHaveTextContent(HERO_FIRST_SENTENCE)
  expect(document.body.textContent || '').not.toContain(NEEDLE)
  cleanup()

  wrap(<Pricing />, '/pricing')
  expect(screen.getByRole('link', { name: /免费注册/ })).toBeInTheDocument()
  expect(document.body.textContent || '').not.toContain(NEEDLE)
  cleanup()

  wrap(<Capabilities />, '/capabilities')
  expect(await screen.findByText('暂无已上架能力')).toBeInTheDocument()
  expect(document.body.textContent || '').not.toContain(NEEDLE)
})
