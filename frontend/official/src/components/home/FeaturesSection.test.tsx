/**
 * T-01 功能介绍：导出当前可买仅 CSV/JSON + 100 条；GWT-70.4 文案。
 */
import React from 'react'
import { render, screen } from '@testing-library/react'

import FeaturesSection from './FeaturesSection'

const FORBIDDEN_GATEWAY = '直连平台网关'
const FORBIDDEN_RELAY_TOKEN = '我的中转令牌'
const FORBIDDEN_CLAIMS = ['抽取准确率', '已校准', '官方认证', '正品保证'] as const

test('test_no_direct_gateway_or_relay_token_copy', () => {
  render(<FeaturesSection />)
  const copy = document.body.textContent || ''
  expect(copy).not.toContain(FORBIDDEN_GATEWAY)
  expect(copy).not.toContain(FORBIDDEN_RELAY_TOKEN)
  expect(screen.queryByRole('link', { name: FORBIDDEN_GATEWAY })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: FORBIDDEN_RELAY_TOKEN })).not.toBeInTheDocument()
})

test('export copy is csv or json with 100 row cap and not excel', () => {
  const { container } = render(<FeaturesSection />)
  const copy = container.textContent || ''
  expect(copy).toMatch(/CSV 或 JSON/)
  expect(copy).toMatch(/单次最多 100 条/)
  expect(copy).not.toMatch(/Excel/i)
  expect(copy).not.toMatch(/xlsx/i)
})

test('test_no_accuracy_or_certification_copy', () => {
  render(<FeaturesSection />)
  const copy = document.body.textContent || ''
  FORBIDDEN_CLAIMS.forEach((phrase) => expect(copy).not.toContain(phrase))
})
