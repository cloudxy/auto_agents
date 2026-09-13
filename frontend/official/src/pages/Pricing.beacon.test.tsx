/**
 * T-12 五档 cta 分格：pricing_pro / register_free / pricing_enterprise 不得合并。
 */
import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

jest.mock('../services/beacon', () => ({
  trackCta: jest.fn(),
  trackPageView: jest.fn(),
}))

import { trackCta } from '../services/beacon'
import Pricing from './Pricing'

function renderPricing() {
  return render(
    <MemoryRouter>
      <Pricing />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  ;(trackCta as jest.Mock).mockClear()
})

test('pricing free CTA is register_free (GWT-15.15)', () => {
  renderPricing()
  fireEvent.click(screen.getByRole('link', { name: /免费注册/ }))
  expect(trackCta).toHaveBeenCalledWith('register_free')
  expect(trackCta).not.toHaveBeenCalledWith('pricing_pro')
})

test('pricing pro CTA is pricing_pro (GWT-15.6)', () => {
  renderPricing()
  const paid = screen.getAllByRole('link', { name: '去结账' })
  fireEvent.click(paid[0])
  expect(trackCta).toHaveBeenCalledWith('pricing_pro')
  expect(trackCta).not.toHaveBeenCalledWith('register_free')
})

test('pricing enterprise CTA is pricing_enterprise (GWT-15.16)', () => {
  renderPricing()
  const paid = screen.getAllByRole('link', { name: '去结账' })
  fireEvent.click(paid[1])
  expect(trackCta).toHaveBeenCalledWith('pricing_enterprise')
  expect(trackCta).not.toHaveBeenCalledWith('pricing_pro')
})
