/**
 * T-12 官网 login / browse_market CTA 与页浏览。
 */
import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

jest.mock('../../services/beacon', () => ({
  trackCta: jest.fn(),
  trackPageView: jest.fn(),
}))

import { trackCta, trackPageView } from '../../services/beacon'
import SiteLayout from './SiteLayout'

test('header login CTA is login (GWT-15.17)', () => {
  render(
    <MemoryRouter initialEntries={['/']}>
      <SiteLayout />
    </MemoryRouter>,
  )
  fireEvent.click(screen.getByRole('link', { name: '管理后台' }))
  expect(trackCta).toHaveBeenCalledWith('login')
})

test('capabilities nav CTA is browse_market (GWT-15.18)', () => {
  render(
    <MemoryRouter initialEntries={['/']}>
      <SiteLayout />
    </MemoryRouter>,
  )
  fireEvent.click(screen.getAllByRole('link', { name: '能力市场' })[0])
  expect(trackCta).toHaveBeenCalledWith('browse_market')
  expect(screen.queryByRole('link', { name: '技能广场' })).not.toBeInTheDocument()
  expect(screen.queryByRole('link', { name: '能力广场' })).not.toBeInTheDocument()
})

test('home pricing register pages emit official_page_viewed (GWT-15.9)', () => {
  render(
    <MemoryRouter initialEntries={['/pricing']}>
      <SiteLayout />
    </MemoryRouter>,
  )
  expect(trackPageView).toHaveBeenCalledWith('pricing')
})
