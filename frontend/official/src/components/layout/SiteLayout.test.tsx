/**
 * T-21 / FR-M33：DUTY_CONTACT 空则访客面无联系 CTA。
 */
import React from 'react'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

jest.mock('../../services/beacon', () => ({
  trackCta: jest.fn(),
  trackPageView: jest.fn(),
}))

import SiteLayout from './SiteLayout'
import { DUTY_CONTACT } from '../../dutyContact'

test('GWT-M33 empty DUTY_CONTACT has no 联系平台 CTA', () => {
  expect(DUTY_CONTACT).toBe('')
  render(
    <MemoryRouter>
      <SiteLayout />
    </MemoryRouter>,
  )
  expect(screen.queryByRole('link', { name: '联系平台' })).toBeNull()
  expect(document.body.textContent || '').not.toContain('mailto:')
  expect(document.body.textContent || '').not.toContain('当前可买')
  expect(document.body.textContent || '').not.toContain('支付已通')
})
