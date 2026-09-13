import React from 'react'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

jest.mock('../../services/usage', () => ({
  fetchUpgradeIntent: jest.fn(),
}))

import { QuotaBlockAlert } from './QuotaBlockAlert'
import {
  PLAN_FULL_COPY,
  SPIDER_WORKER_OFFLINE_COPY,
  STORAGE_CTA,
  UPGRADE_CTA,
} from '../../constants/collectCopy'

test('storage CTA is 去结果库 and never worker copy', () => {
  render(
    <MemoryRouter>
      <QuotaBlockAlert cta={STORAGE_CTA} />
    </MemoryRouter>,
  )
  expect(screen.getByText(PLAN_FULL_COPY)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: STORAGE_CTA })).toHaveAttribute('href', '/data')
  expect(screen.queryByText(SPIDER_WORKER_OFFLINE_COPY)).toBeNull()
  expect(document.body.textContent).not.toContain('当前可买')
})

test('token CTA is 申请提升 not 申请提升配额 and not worker', () => {
  render(
    <MemoryRouter>
      <QuotaBlockAlert cta={UPGRADE_CTA} />
    </MemoryRouter>,
  )
  expect(screen.getByRole('button', { name: UPGRADE_CTA })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '申请提升配额' })).toBeNull()
  expect(screen.queryByText(SPIDER_WORKER_OFFLINE_COPY)).toBeNull()
})
