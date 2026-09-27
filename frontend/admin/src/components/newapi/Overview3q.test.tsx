/**
 * T-27 / FR-U25 值班三态：空 / 降级 / 活 互斥；行「活」；加载失败 ≠ 空；
 * 伪装不把渠道打成自动禁用。禁句「暂无渠道」。
 */
import React from 'react'
import { render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

jest.mock('../../services/newapi', () => ({
  fetchNewapiOverview: jest.fn(),
  fetchChannelsWithConfig: jest.fn(),
  fetchNewapiEvents: jest.fn(),
  fetchNewapiProbeResults: jest.fn(),
  triggerNewapiProbe: jest.fn(),
  CHANNEL_STATUS: { ENABLED: 1, MANUALLY_DISABLED: 2, AUTO_DISABLED: 3 },
}))

import {
  fetchChannelsWithConfig, fetchNewapiEvents, fetchNewapiOverview,
  fetchNewapiProbeResults, triggerNewapiProbe,
} from '../../services/newapi'
import Overview3q from './Overview3q'
import {
  DUTY_DEGRADE_71_3, DUTY_EMPTY_71_2, DUTY_LIVE, DUTY_LOAD_FAILED,
  FORBIDDEN_CHANNEL_EMPTY, isDutyLiveRow, resolveDutyBanner, showDutyLiveRow,
} from './newapiShared'

const overview = fetchNewapiOverview as jest.Mock
const channels = fetchChannelsWithConfig as jest.Mock
const events = fetchNewapiEvents as jest.Mock
const probes = fetchNewapiProbeResults as jest.Mock
const trigger = triggerNewapiProbe as jest.Mock

const NOW = new Date(Date.now() - 5 * 60 * 1000).toISOString()

const ov = (patch: Record<string, unknown> = {}) => ({
  available: true,
  empty_state: null,
  degrade_state: null,
  models: [],
  deployments: [],
  channels: [],
  total: 0,
  events_24h: 0,
  latest_batch_id: null,
  latest_batch_verdicts: {},
  ...patch,
})

const channelRow = (model: string) => ({
  gateway_ref: `dep-${model}`,
  model_name: model,
  api_base: 'https://upstream.test/v1',
  api_key_masked: 'sk***x',
  effective: { limit_quota: 5000, window_hours: 24, cooldown_seconds: 3600 },
  effective_source: 'channel',
  config: null,
})

const probeRow = (model: string, verdict: 'original' | 'spoofed' | 'offline') => ({
  id: 1,
  channel_id: 7,
  model,
  verdict,
  latency_ms: verdict === 'offline' ? null : 120,
  batch_id: 'b-live',
  created_at: NOW,
  scores: {},
})

beforeEach(() => {
  overview.mockReset()
  channels.mockReset()
  events.mockReset().mockResolvedValue({ total: 0, items: [] })
  probes.mockReset().mockResolvedValue({ total: 0, items: [] })
  trigger.mockReset().mockResolvedValue({
    accepted: true, gateway_ref: 'dep-gpt-4o', batch_id: 'manual-t1', reason: null,
  })
})

function renderOverview() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <Overview3q onOpenConfig={jest.fn()} onJumpToEvent={jest.fn()} />
    </QueryClientProvider>,
  )
}

test('resolveDutyBanner: empty / degrade / live / error are mutually exclusive', () => {
  expect(resolveDutyBanner({
    loading: false, error: true, available: true, modelTotal: 0, hasLiveRow: false,
  })).toBe('error')
  expect(resolveDutyBanner({
    loading: false, error: false, available: false, modelTotal: 0, hasLiveRow: false,
  })).toBe('degrade')
  expect(resolveDutyBanner({
    loading: false, error: false, available: false, modelTotal: 0, hasLiveRow: true,
  })).toBe('live')
  expect(resolveDutyBanner({
    loading: false, error: false, available: true, modelTotal: 0, hasLiveRow: true,
  })).toBe('live')
  expect(resolveDutyBanner({
    loading: false, error: false, available: true, modelTotal: 0, hasLiveRow: false,
  })).toBe('empty')
  expect(resolveDutyBanner({
    loading: false, error: false, available: true, modelTotal: 2, hasLiveRow: true,
  })).toBe('live')
})

test('resolveDutyBanner: hasLiveRow overrides empty/degrade duty_page_state; error still wins', () => {
  expect(resolveDutyBanner({
    loading: false, error: false, available: true, modelTotal: 0, hasLiveRow: false,
    dutyPageState: 'live',
  })).toBe('live')
  expect(resolveDutyBanner({
    loading: false, error: false, available: true, modelTotal: 2, hasLiveRow: true,
    dutyPageState: 'empty',
  })).toBe('live')
  expect(resolveDutyBanner({
    loading: false, error: false, available: true, modelTotal: 0, hasLiveRow: false,
    dutyPageState: 'degrade',
  })).toBe('degrade')
  expect(resolveDutyBanner({
    loading: false, error: true, available: true, modelTotal: 1, hasLiveRow: true,
    dutyPageState: 'live',
  })).toBe('error')
})

test('isDutyLiveRow requires reachable gateway, registered model, original verdict', () => {
  expect(isDutyLiveRow(true, true, 'original')).toBe(true)
  expect(isDutyLiveRow(true, true, 'spoofed')).toBe(false)
  expect(isDutyLiveRow(true, false, 'original')).toBe(false)
  expect(isDutyLiveRow(false, true, 'original')).toBe(false)
})

test('showDutyLiveRow requires gatewayAvailable and API live or local original', () => {
  expect(showDutyLiveRow({
    dutyRowStatus: 'live', dutyRowStatusText: DUTY_LIVE,
    gatewayAvailable: false, registered: false, verdict: 'spoofed',
  })).toBe(false)
  expect(showDutyLiveRow({
    dutyRowStatus: 'live', dutyRowStatusText: DUTY_LIVE,
    gatewayAvailable: true, registered: false, verdict: 'spoofed',
  })).toBe(true)
  expect(showDutyLiveRow({
    dutyRowStatus: 'spoofed', dutyRowStatusText: null,
    gatewayAvailable: true, registered: true, verdict: 'original',
  })).toBe(false)
  expect(showDutyLiveRow({
    gatewayAvailable: true, registered: true, verdict: 'original',
  })).toBe(true)
  expect(showDutyLiveRow({
    gatewayAvailable: false, registered: true, verdict: 'original',
  })).toBe(false)
})

test('GWT-U25.1 live row shows 活 and not empty/degrade/暂无渠道', async () => {
  overview.mockResolvedValue(ov({
    available: true,
    duty_page_state: 'live',
    models: [{
      gateway_ref: 'dep-gpt-4o', model_name: 'gpt-4o',
      duty_row_status: 'live', duty_row_status_text: DUTY_LIVE,
    }],
    total: 1,
    latest_batch_verdicts: { original: 1 },
  }))
  channels.mockResolvedValue([channelRow('gpt-4o')])
  probes.mockResolvedValue({ total: 1, items: [probeRow('gpt-4o', 'original')] })
  renderOverview()
  expect(await screen.findByTestId('duty-live')).toBeInTheDocument()
  expect(screen.getByText(DUTY_LIVE)).toBeInTheDocument()
  const row = screen.getByText('gpt-4o').closest('tr') as HTMLElement
  expect(within(row).getByText(DUTY_LIVE)).toBeInTheDocument()
  expect(screen.queryByTestId('duty-banner-empty')).not.toBeInTheDocument()
  expect(screen.queryByTestId('duty-banner-degrade')).not.toBeInTheDocument()
  expect(screen.queryByText(DUTY_EMPTY_71_2)).not.toBeInTheDocument()
  expect(screen.queryByText(DUTY_DEGRADE_71_3)).not.toBeInTheDocument()
  expect(screen.queryByText(FORBIDDEN_CHANNEL_EMPTY)).not.toBeInTheDocument()
  expect(screen.queryByText(DUTY_LOAD_FAILED)).not.toBeInTheDocument()
  expect(document.body.textContent || '').not.toContain('当前可买')
})

test('GWT-U25.2 empty is not load failure and forbids 暂无渠道', async () => {
  overview.mockResolvedValue(ov({
    available: true,
    duty_page_state: 'empty',
    empty_state: DUTY_EMPTY_71_2,
    total: 0,
  }))
  channels.mockResolvedValue([])
  renderOverview()
  expect(await screen.findByTestId('duty-banner-empty')).toBeInTheDocument()
  expect(screen.getByText(DUTY_EMPTY_71_2)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /刷\s*新/ })).toBeInTheDocument()
  expect(screen.queryByTestId('duty-banner-degrade')).not.toBeInTheDocument()
  expect(screen.queryByTestId('duty-live')).not.toBeInTheDocument()
  expect(screen.queryByText(DUTY_LIVE)).not.toBeInTheDocument()
  expect(screen.queryByText(DUTY_DEGRADE_71_3)).not.toBeInTheDocument()
  expect(screen.queryByText(DUTY_LOAD_FAILED)).not.toBeInTheDocument()
  expect(screen.queryByText(FORBIDDEN_CHANNEL_EMPTY)).not.toBeInTheDocument()
})

test('GWT-U25.4 degrade keeps local probes, no empty title, no 活, no 暂无渠道', async () => {
  overview.mockResolvedValue(ov({
    available: false,
    duty_page_state: 'degrade',
    reason: DUTY_DEGRADE_71_3,
    degrade_state: DUTY_DEGRADE_71_3,
    empty_state: DUTY_EMPTY_71_2,
    total: 0,
    events_24h: 4,
  }))
  channels.mockResolvedValue([])
  probes.mockResolvedValue({ total: 1, items: [probeRow('local-echo', 'original')] })
  renderOverview()
  expect(await screen.findByTestId('duty-banner-degrade')).toBeInTheDocument()
  expect(screen.getByText(DUTY_DEGRADE_71_3)).toBeInTheDocument()
  expect(screen.getByText('local-echo')).toBeInTheDocument()
  expect(screen.queryByTestId('duty-banner-empty')).not.toBeInTheDocument()
  expect(screen.queryByText(DUTY_EMPTY_71_2)).not.toBeInTheDocument()
  expect(screen.queryByTestId('duty-live')).not.toBeInTheDocument()
  expect(screen.queryByText(DUTY_LIVE)).not.toBeInTheDocument()
  expect(screen.queryByText(FORBIDDEN_CHANNEL_EMPTY)).not.toBeInTheDocument()
  expect(screen.queryByText(DUTY_LOAD_FAILED)).not.toBeInTheDocument()
})

test('load fail is not empty and not 暂无渠道', async () => {
  overview.mockRejectedValue(new Error('network'))
  channels.mockResolvedValue([])
  renderOverview()
  expect(await screen.findByText(DUTY_LOAD_FAILED)).toBeInTheDocument()
  expect(screen.queryByTestId('duty-banner-empty')).not.toBeInTheDocument()
  expect(screen.queryByTestId('duty-banner-degrade')).not.toBeInTheDocument()
  expect(screen.queryByText(DUTY_EMPTY_71_2)).not.toBeInTheDocument()
  expect(screen.queryByText(DUTY_DEGRADE_71_3)).not.toBeInTheDocument()
  expect(screen.queryByText(FORBIDDEN_CHANNEL_EMPTY)).not.toBeInTheDocument()
  expect(screen.queryByText(DUTY_LIVE)).not.toBeInTheDocument()
})

test('spoofed tag does not flip channel to auto-disabled and is not 活', async () => {
  overview.mockResolvedValue(ov({
    available: true,
    models: [{ gateway_ref: 'dep-gpt-4o', model_name: 'gpt-4o' }],
    total: 1,
    latest_batch_verdicts: { spoofed: 1 },
  }))
  channels.mockResolvedValue([channelRow('gpt-4o')])
  probes.mockResolvedValue({ total: 1, items: [probeRow('gpt-4o', 'spoofed')] })
  renderOverview()
  expect(await screen.findByText('gpt-4o')).toBeInTheDocument()
  const row = screen.getByText('gpt-4o').closest('tr') as HTMLElement
  expect(within(row).getByText('伪装')).toBeInTheDocument()
  expect(within(row).queryByText(DUTY_LIVE)).not.toBeInTheDocument()
  expect(screen.queryByTestId('duty-live')).not.toBeInTheDocument()
  expect(screen.queryByText('自动禁用')).not.toBeInTheDocument()
  expect(screen.queryByText('人工禁用')).not.toBeInTheDocument()
  expect(within(screen.getByTestId('overview-3q-channels')).queryByRole('button', { name: /禁\s*用/ })).toBeNull()
  expect(screen.queryByText(DUTY_EMPTY_71_2)).not.toBeInTheDocument()
  expect(screen.queryByText(DUTY_DEGRADE_71_3)).not.toBeInTheDocument()
  expect(screen.queryByText(FORBIDDEN_CHANNEL_EMPTY)).not.toBeInTheDocument()
})

test('a live row hides empty copy even if overview.total is 0', async () => {
  overview.mockResolvedValue(ov({
    available: true,
    empty_state: DUTY_EMPTY_71_2,
    total: 0,
  }))
  channels.mockResolvedValue([channelRow('gpt-4o')])
  probes.mockResolvedValue({ total: 1, items: [probeRow('gpt-4o', 'original')] })
  renderOverview()
  expect(await screen.findByTestId('duty-live')).toBeInTheDocument()
  expect(screen.queryByTestId('duty-banner-empty')).not.toBeInTheDocument()
  expect(screen.queryByText(DUTY_EMPTY_71_2)).not.toBeInTheDocument()
  expect(screen.queryByTestId('duty-banner-degrade')).not.toBeInTheDocument()
})

test('duty_page_state empty plus a live row must not show empty copy', async () => {
  overview.mockResolvedValue(ov({
    available: true,
    duty_page_state: 'empty',
    empty_state: DUTY_EMPTY_71_2,
    total: 0,
  }))
  channels.mockResolvedValue([channelRow('gpt-4o')])
  probes.mockResolvedValue({ total: 1, items: [probeRow('gpt-4o', 'original')] })
  renderOverview()
  expect(await screen.findByTestId('duty-live')).toBeInTheDocument()
  expect(screen.queryByTestId('duty-banner-empty')).not.toBeInTheDocument()
  expect(screen.queryByText(DUTY_EMPTY_71_2)).not.toBeInTheDocument()
  expect(screen.queryByTestId('duty-banner-degrade')).not.toBeInTheDocument()
  expect(screen.queryByText(FORBIDDEN_CHANNEL_EMPTY)).not.toBeInTheDocument()
})

test('prefers duty_page_state live and duty_row_status_text 活 without local probes', async () => {
  overview.mockResolvedValue(ov({
    available: true,
    duty_page_state: 'live',
    empty_state: DUTY_EMPTY_71_2,
    models: [{
      gateway_ref: 'dep-gpt-4o', model_name: 'gpt-4o',
      duty_row_status: 'live', duty_row_status_text: DUTY_LIVE,
    }],
    total: 1,
  }))
  channels.mockResolvedValue([channelRow('gpt-4o')])
  renderOverview()
  expect(await screen.findByTestId('duty-live')).toBeInTheDocument()
  const row = screen.getByText('gpt-4o').closest('tr') as HTMLElement
  expect(within(row).getByText(DUTY_LIVE)).toBeInTheDocument()
  expect(screen.queryByTestId('duty-banner-empty')).not.toBeInTheDocument()
  expect(screen.queryByText(DUTY_EMPTY_71_2)).not.toBeInTheDocument()
  expect(screen.queryByTestId('duty-banner-degrade')).not.toBeInTheDocument()
  expect(screen.queryByText(FORBIDDEN_CHANNEL_EMPTY)).not.toBeInTheDocument()
})

test('prefers duty_page_state degrade over local empty derivation', async () => {
  overview.mockResolvedValue(ov({
    available: true,
    duty_page_state: 'degrade',
    degrade_state: DUTY_DEGRADE_71_3,
    empty_state: DUTY_EMPTY_71_2,
    total: 0,
  }))
  channels.mockResolvedValue([])
  renderOverview()
  expect(await screen.findByTestId('duty-banner-degrade')).toBeInTheDocument()
  expect(screen.getByText(DUTY_DEGRADE_71_3)).toBeInTheDocument()
  expect(screen.queryByTestId('duty-banner-empty')).not.toBeInTheDocument()
  expect(screen.queryByText(DUTY_EMPTY_71_2)).not.toBeInTheDocument()
  expect(screen.queryByTestId('duty-live')).not.toBeInTheDocument()
})

test('prefers API duty_row_status spoofed over local original probe', async () => {
  overview.mockResolvedValue(ov({
    available: true,
    duty_page_state: null,
    models: [{
      gateway_ref: 'dep-gpt-4o', model_name: 'gpt-4o',
      duty_row_status: 'spoofed', duty_row_status_text: null,
    }],
    total: 1,
    latest_batch_verdicts: { original: 1 },
  }))
  channels.mockResolvedValue([channelRow('gpt-4o')])
  probes.mockResolvedValue({ total: 1, items: [probeRow('gpt-4o', 'original')] })
  renderOverview()
  expect(await screen.findByText('gpt-4o')).toBeInTheDocument()
  const row = screen.getByText('gpt-4o').closest('tr') as HTMLElement
  expect(within(row).queryByText(DUTY_LIVE)).not.toBeInTheDocument()
  expect(screen.queryByTestId('duty-live')).not.toBeInTheDocument()
  expect(screen.queryByText(DUTY_EMPTY_71_2)).not.toBeInTheDocument()
  expect(screen.queryByText(DUTY_DEGRADE_71_3)).not.toBeInTheDocument()
})
