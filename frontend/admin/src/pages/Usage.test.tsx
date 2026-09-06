import React from 'react'
import { render, screen } from '@testing-library/react'
import { withQuery } from '../testUtils'

jest.mock('../services/usage', () => ({
  fetchUsageOverview: jest.fn().mockResolvedValue({
    tenant_id: 1,
    quota: { task_concurrency: 5, result_storage: 10, llm_tokens_month: 100 },
    usage: { task_concurrency: 1, result_storage: 2, llm_tokens_month: 3 },
    llm_by_provider: {},
    cost_by_provider: {},
    cost_cents_total: 0,
  }),
  fetchUsageByMember: jest.fn().mockResolvedValue([]),
  fetchDeliveryWebhook: jest.fn().mockResolvedValue({ delivery_webhook_url: null }),
  putDeliveryWebhook: jest.fn(),
}))

jest.mock('../services/billing', () => ({
  CHANNEL_LABEL: { offline: '线下转账', alipay: '支付宝', wechat: '微信支付' },
  listPlans: jest.fn().mockResolvedValue([]),
  fetchSubscription: jest.fn().mockResolvedValue(null),
  listMyOrders: jest.fn().mockResolvedValue([]),
  createOrder: jest.fn(),
}))

import Usage from './Usage'

test('renders usage quota cards', async () => {
  render(withQuery(<Usage />))
  expect(await screen.findByText('任务并发')).toBeInTheDocument()
  expect(await screen.findByText('任务交付 Webhook')).toBeInTheDocument()
  expect(await screen.findByText('套餐与订购')).toBeInTheDocument()
})
