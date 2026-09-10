/**
 * T-18 值班页：71.2 空态 / 71.3 降级；无完整 Key；禁止「暂无渠道」
 */
import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'

jest.mock('../services/newapi', () => ({
  fetchNewapiOverview: jest.fn(),
  fetchChannelsWithConfig: jest.fn(),
  fetchNewapiEvents: jest.fn().mockResolvedValue({ total: 1, items: [{
    id: 1, channel_id: 7, action: 'disabled', source: 'scheduler', created_at: '2026-09-01T00:00:00',
  }] }),
  fetchNewapiProbeResults: jest.fn().mockResolvedValue({ total: 1, items: [{
    id: 2, channel_id: 7, model: 'gpt-4o', verdict: 'original', batch_id: 'b1',
    scores: {}, latency_ms: 10, created_at: '2026-09-01T00:00:00',
  }] }),
  setModelConfig: jest.fn(),
  clearModelConfig: jest.fn(),
  CHANNEL_STATUS: { ENABLED: 1, MANUALLY_DISABLED: 2, AUTO_DISABLED: 3 },
}))

import {
  fetchChannelsWithConfig,
  fetchNewapiOverview,
} from '../services/newapi'
import NewApiOps from './NewApiOps'
import {
  DUTY_DEGRADE_71_3,
  DUTY_EMPTY_71_2,
  FORBIDDEN_CHANNEL_EMPTY,
} from '../components/newapi/newapiShared'

const overview = fetchNewapiOverview as jest.Mock
const channels = fetchChannelsWithConfig as jest.Mock

beforeEach(() => {
  overview.mockReset()
  channels.mockReset()
})

test('GWT-71.2 reachable zero models is empty not load failure', async () => {
  overview.mockResolvedValue({
    available: true,
    empty_state: DUTY_EMPTY_71_2,
    degrade_state: null,
    models: [],
    deployments: [],
    channels: [],
    total: 0,
    events_24h: 2,
    latest_batch_id: null,
    latest_batch_verdicts: {},
  })
  channels.mockResolvedValue([])
  render(<NewApiOps />)
  expect(await screen.findByText(DUTY_EMPTY_71_2)).toBeInTheDocument()
  expect(screen.getByText(/平台 LLM 网关已连通/)).toBeInTheDocument()
  expect(screen.queryByText(FORBIDDEN_CHANNEL_EMPTY)).not.toBeInTheDocument()
  expect(screen.queryByText(/加载失败/)).not.toBeInTheDocument()
  expect(screen.queryByText(DUTY_DEGRADE_71_3)).not.toBeInTheDocument()
})

test('GWT-71.3 unreachable shows degrade and keeps local probes/events', async () => {
  overview.mockResolvedValue({
    available: false,
    reason: DUTY_DEGRADE_71_3,
    empty_state: null,
    degrade_state: DUTY_DEGRADE_71_3,
    models: [],
    deployments: [],
    channels: [],
    total: 0,
    events_24h: 4,
    latest_batch_id: 'batch-local',
    latest_batch_verdicts: { original: 1 },
  })
  channels.mockResolvedValue([])
  render(<NewApiOps />)
  expect(await screen.findByText(DUTY_DEGRADE_71_3)).toBeInTheDocument()
  expect(screen.getByText(/现在读不到网关侧模型/)).toBeInTheDocument()
  expect(screen.getByText('4')).toBeInTheDocument()
  expect(screen.queryByText(FORBIDDEN_CHANNEL_EMPTY)).not.toBeInTheDocument()
  expect(screen.queryByText(DUTY_EMPTY_71_2)).not.toBeInTheDocument()
  expect(screen.getByText('探针')).toBeInTheDocument()
  expect(screen.getByText('事件')).toBeInTheDocument()
})

test('GWT-71.1 lists gateway models without full upstream key', async () => {
  overview.mockResolvedValue({
    available: true,
    empty_state: null,
    degrade_state: null,
    models: [{
      gateway_ref: 'dep-gpt-4o', model_name: 'gpt-4o',
      api_base: 'https://upstream.test/v1', api_key_masked: 'sk***leak',
    }],
    deployments: [],
    channels: [],
    total: 1,
    events_24h: 0,
    latest_batch_verdicts: {},
  })
  channels.mockResolvedValue([{
    gateway_ref: 'dep-gpt-4o', model_name: 'gpt-4o',
    api_base: 'https://upstream.test/v1', api_key_masked: 'sk***leak',
    effective: { limit_quota: 0, window_hours: 24, cooldown_seconds: 3600 },
    effective_source: 'none',
    config: null,
  }])
  render(<NewApiOps />)
  expect(await screen.findByText('gpt-4o')).toBeInTheDocument()
  expect(screen.getByText('sk***leak')).toBeInTheDocument()
  expect(screen.queryByText('sk-secret-should-not-leak')).not.toBeInTheDocument()
  await waitFor(() => {
    expect(screen.queryByText(FORBIDDEN_CHANNEL_EMPTY)).not.toBeInTheDocument()
  })
})
