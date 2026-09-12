/**
 * T-18 值班页：71.2 空态 / 71.3 降级；无完整 Key；禁止「暂无渠道」
 * T-31 页头结构（GWT-98.1）：三 tab 上提顶栏行、页内无标题卡、内容区直接开始。
 * T-32 三问驾驶舱（GWT-98.2 同屏三问 / 98.3 置顶排序 / 98.5 事件跳转 / 98.6 不可达）
 * 与三区独立失败；T-33 立即探测（GWT-98.4 行内进行中 + 完成行内更新）。
 * T-32 起 Overview3q 走 react-query：渲染必须包 QueryClientProvider（retry:false）。
 */
import React from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import AdminLayout from '../components/AdminLayout'
import { useAuthStore } from '../store/useAuthStore'

jest.mock('../services/newapi', () => ({
  fetchNewapiOverview: jest.fn(),
  fetchChannelsWithConfig: jest.fn(),
  fetchNewapiEvents: jest.fn(),
  fetchNewapiProbeResults: jest.fn(),
  triggerNewapiProbe: jest.fn(),
  setModelConfig: jest.fn(),
  clearModelConfig: jest.fn(),
  CHANNEL_STATUS: { ENABLED: 1, MANUALLY_DISABLED: 2, AUTO_DISABLED: 3 },
}))

// AdminLayout 集成渲染（GWT-98.1 顶栏行）只需权限快照端点成功；其余端点拒绝
jest.mock('../services/api', () => ({
  __esModule: true,
  unwrap: (envelope: { data?: unknown }) => envelope?.data,
  default: {
    get: jest.fn((url: string) =>
      url === '/auth/permissions'
        ? Promise.resolve({ success: true, code: 'OK', message: 'ok', data: ['menu:newapi'] })
        : Promise.reject(new Error('mock network'))),
    post: jest.fn(() => Promise.reject(new Error('mock network'))),
    put: jest.fn(() => Promise.reject(new Error('mock network'))),
    patch: jest.fn(() => Promise.reject(new Error('mock network'))),
    delete: jest.fn(() => Promise.reject(new Error('mock network'))),
  },
}))

import {
  fetchChannelsWithConfig, fetchNewapiEvents, fetchNewapiOverview,
  fetchNewapiProbeResults, triggerNewapiProbe,
} from '../services/newapi'
import NewApiOps from './NewApiOps'
import {
  DUTY_DEGRADE_71_3, DUTY_EMPTY_71_2, DUTY_LOCAL_PROBE_EMPTY, EVENTS_24H_EMPTY,
  FORBIDDEN_CHANNEL_EMPTY, PROBE_LATEST_BATCH_LABEL, PROBE_SPOOF_SUMMARY,
} from '../components/newapi/newapiShared'

const overview = fetchNewapiOverview as jest.Mock
const channels = fetchChannelsWithConfig as jest.Mock
const events = fetchNewapiEvents as jest.Mock
const probes = fetchNewapiProbeResults as jest.Mock
const trigger = triggerNewapiProbe as jest.Mock

// 事件/探针时间戳：相对真实时钟取「5 分钟前」的 UTC ISO——绝对时间戳会在时钟
// 越过其 +24h 后掉出 Overview3q 的 24h 窗口（GWT-98.2 回归根因），相对值恒在窗内
const NOW = new Date(Date.now() - 5 * 60 * 1000).toISOString()
const DEFAULT_EVENT = {
  id: 1, channel_id: 7, action: 'disabled', source: 'scheduler', created_at: NOW,
}
const DEFAULT_PROBE = {
  id: 2, channel_id: 7, model: 'probe-echo', verdict: 'original', batch_id: 'b1',
  scores: {}, latency_ms: 10, created_at: NOW,
}

beforeEach(() => {
  overview.mockReset()
  channels.mockReset()
  events.mockReset().mockResolvedValue({ total: 1, items: [DEFAULT_EVENT] })
  probes.mockReset().mockResolvedValue({ total: 1, items: [DEFAULT_PROBE] })
  trigger.mockReset().mockResolvedValue({
    accepted: true, gateway_ref: 'dep-gpt-4o', batch_id: 'manual-t1', reason: null,
  })
})

function renderOps() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <NewApiOps />
    </QueryClientProvider>,
  )
}

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
  renderOps()
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
  renderOps()
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
  renderOps()
  expect(await screen.findByText('gpt-4o')).toBeInTheDocument()
  expect(screen.getByText('sk***leak')).toBeInTheDocument()
  expect(screen.queryByText('sk-secret-should-not-leak')).not.toBeInTheDocument()
  await waitFor(() => {
    expect(screen.queryByText(FORBIDDEN_CHANNEL_EMPTY)).not.toBeInTheDocument()
  })
})

test('GWT-98.1 page tabs sit in the header row with the welcome text; content starts directly', async () => {
  useAuthStore.setState({
    token: 't', isAuthenticated: true, rememberMe: false,
    user: {
      access_token: 't', token_type: 'bearer', username: 'root',
      is_admin: true, role: 'admin', is_platform_admin: true, tenant_id: null,
    },
  })
  overview.mockResolvedValue({
    available: true, empty_state: null, degrade_state: null,
    models: [], deployments: [], channels: [],
    total: 2, events_24h: 3, latest_batch_id: 'batch-1', latest_batch_verdicts: { original: 1 },
  })
  channels.mockResolvedValue([])

  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const { container } = render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/newapi']}>
        <Routes>
          <Route element={<AdminLayout />}>
            <Route path="/newapi" element={<NewApiOps />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  const header = container.querySelector('.ant-layout-header') as HTMLElement
  const content = container.querySelector('.ant-layout-content') as HTMLElement
  expect(header).not.toBeNull()
  expect(content).not.toBeNull()

  // 顶栏行 = 页名 + 三 tab + 欢迎语（同一行，GWT-98.1）
  await within(header).findByRole('tab', { name: /总览/ })
  expect(within(header).getByRole('tab', { name: /探针/ })).toBeInTheDocument()
  expect(within(header).getByRole('tab', { name: /事件/ })).toBeInTheDocument()
  expect(within(header).getByText('中转站管控')).toBeInTheDocument()
  expect(within(header).getByText(/欢迎回来/)).toBeInTheDocument()

  // tab 不在内容区；内容区直接以当前 tab 内容开始
  expect(within(content).queryAllByRole('tab')).toHaveLength(0)
  expect(await within(content).findByText('近 24h 事件数')).toBeInTheDocument()

  // 页内不再有复述页名的标题卡/旧标题「LLM 网关值班」
  expect(screen.queryByText('LLM 网关值班')).not.toBeInTheDocument()

  // T-32：总览三问分区容器落位（三区结构）
  expect(within(content).getByTestId('overview-3q')).toBeInTheDocument()
  expect(within(content).getByTestId('overview-3q-health')).toBeInTheDocument()
  expect(within(content).getByTestId('overview-3q-channels')).toBeInTheDocument()
  expect(within(content).getByTestId('overview-3q-events')).toBeInTheDocument()
})

test('GWT-98.1 fallback tabs stay usable standalone and switching only toggles content panes', async () => {
  overview.mockResolvedValue({
    available: true, empty_state: null, degrade_state: null,
    models: [], deployments: [], channels: [],
    total: 1, events_24h: 0, latest_batch_verdicts: {},
  })
  channels.mockResolvedValue([])

  renderOps()
  // 无 AdminLayout 槽位时 tab 原位回退（单测/独立渲染可用性不变）
  expect(await screen.findByText('近 24h 事件数')).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: /总览/ })).toHaveAttribute('aria-selected', 'true')
  expect(screen.getByRole('button', { name: /刷新/ })).toBeInTheDocument()

  // 切到探针：只动内容区（探针数据可见、总览统计隐藏），pane 常挂载不卸载
  fireEvent.click(screen.getByRole('tab', { name: /探针/ }))
  expect(await screen.findByText('b1')).toBeVisible()
  expect(screen.getByText('近 24h 事件数')).not.toBeVisible()
  expect(screen.getByRole('tab', { name: /探针/ })).toHaveAttribute('aria-selected', 'true')

  // 页内无旧标题卡
  expect(screen.queryByText('LLM 网关值班')).not.toBeInTheDocument()
})

test('GWT-98.2 three questions on one screen: health/models, per-channel verdict+latency+events+budget, top events', async () => {
  overview.mockResolvedValue({
    available: true, empty_state: null, degrade_state: null,
    models: [
      { gateway_ref: 'dep-gpt-4o', model_name: 'gpt-4o' },
      { gateway_ref: 'dep-claude', model_name: 'claude-3' },
    ],
    deployments: [{ gateway_ref: 'dep-d1', model_name: 'gpt-4o-deploy' }],
    channels: [],
    total: 2, events_24h: 3, latest_batch_id: 'batch-9',
    latest_batch_verdicts: { original: 1 },
  })
  channels.mockResolvedValue([{
    gateway_ref: 'dep-gpt-4o', model_name: 'gpt-4o',
    api_base: 'https://upstream.test/v1', api_key_masked: 'sk***x',
    effective: { limit_quota: 5000, window_hours: 24, cooldown_seconds: 3600 },
    effective_source: 'channel',
    config: null,
  }])
  probes.mockResolvedValue({
    total: 1,
    items: [{
      id: 9, channel_id: 7, model: 'gpt-4o', verdict: 'original', latency_ms: 120,
      batch_id: 'batch-9', created_at: NOW, scores: {},
    }],
  })
  events.mockResolvedValue({
    total: 1,
    items: [{
      id: 11, channel_id: 7, action: 'budget_enforced', usage: 4200, limit_quota: 5000,
      window_hours: 24, reason: 'spend-4200', source: 'scheduler', created_at: NOW,
    }],
  })

  renderOps()
  // 第一问：健康灯 + 模型数 + 部署摘要
  expect(await screen.findByText('可用')).toBeInTheDocument()
  const healthRegion = screen.getByTestId('overview-3q-health')
  expect(within(healthRegion).getByText('模型/部署')).toBeInTheDocument()
  expect(within(healthRegion).getByText('部署 1 个')).toBeInTheDocument()
  // 第二问：判定 + 延迟 + 24h 事件数 + 窗口用量（已用/额度）
  expect(screen.getByText('正品')).toBeInTheDocument()
  expect(screen.getByText('120 ms')).toBeInTheDocument()
  const channelRow = screen.getByText('gpt-4o').closest('tr') as HTMLElement
  expect(channelRow).not.toBeNull()
  expect(within(channelRow).getByText('1')).toBeInTheDocument() // 24h 事件
  expect(screen.getByText('4,200')).toBeInTheDocument() // 已用（事件快照，来源 tooltip 悬停可见）
  expect(channelRow.textContent).toContain('5,000') // 额度（窗口用量与额度调度两列同源同值）
  // 第三问：最近事件 Top N + 近 24h 事件数
  expect(screen.getByText('spend-4200')).toBeInTheDocument()
  expect(screen.getByText('近 24h 事件数')).toBeInTheDocument()
})

test('GWT-98.3 spoofed and offline channels are pinned before original ones', async () => {
  overview.mockResolvedValue({
    available: true, empty_state: null, degrade_state: null,
    models: [], deployments: [], channels: [],
    total: 3, events_24h: 0, latest_batch_verdicts: { original: 1, spoofed: 1, offline: 1 },
  })
  channels.mockResolvedValue(['model-a', 'model-b', 'model-c'].map((model) => ({
    gateway_ref: `dep-${model}`, model_name: model,
    effective: { limit_quota: 1000, window_hours: 24, cooldown_seconds: 3600 },
    effective_source: 'global',
    config: null,
  })))
  probes.mockResolvedValue({
    total: 3,
    items: [
      { id: 1, channel_id: 101, model: 'model-a', verdict: 'original', latency_ms: 50, batch_id: 'b1', created_at: NOW, scores: {} },
      { id: 2, channel_id: 102, model: 'model-b', verdict: 'spoofed', latency_ms: 80, batch_id: 'b1', created_at: NOW, scores: {} },
      { id: 3, channel_id: 103, model: 'model-c', verdict: 'offline', latency_ms: null, batch_id: 'b1', created_at: NOW, scores: {} },
    ],
  })

  renderOps()
  expect(await screen.findByText('model-a')).toBeInTheDocument()
  const channelsRegion = screen.getByTestId('overview-3q-channels')
  const bodyRows = within(channelsRegion)
    .getAllByRole('row')
    .filter((row) => row.querySelector('td'))
  expect(bodyRows).toHaveLength(3)
  expect(bodyRows[0]).toHaveTextContent('伪装')
  expect(bodyRows[1]).toHaveTextContent('不可用')
  expect(bodyRows[2]).toHaveTextContent('正品')
})

test('GWT-98.4 edge: one region failing does not take down other regions (FR-84 sentences + retry)', async () => {
  overview.mockResolvedValue({
    available: true, empty_state: null, degrade_state: null,
    models: [], deployments: [], channels: [],
    total: 1, events_24h: 0, latest_batch_verdicts: { original: 1 },
  })
  channels.mockResolvedValue([{
    gateway_ref: 'dep-gpt-4o', model_name: 'gpt-4o',
    effective: { limit_quota: 5000, window_hours: 24, cooldown_seconds: 3600 },
    effective_source: 'channel',
    config: null,
  }])
  events
    .mockRejectedValueOnce(new Error('events down'))
    .mockResolvedValue({
      total: 1,
      items: [{
        id: 21, channel_id: 7, action: 'disabled', reason: '事件重试成功',
        source: 'scheduler', created_at: NOW,
      }],
    })

  renderOps()
  // 事件区失败句 + 重试（FR-84 同句式）；健康区/渠道区不受拖垮
  expect(await screen.findByText('事件列表加载失败。检查网络后重试。')).toBeInTheDocument()
  expect(screen.getByText('可用')).toBeInTheDocument()
  expect(screen.getByText('正品')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /重\s*试/ }))
  expect(await screen.findByText('事件重试成功')).toBeInTheDocument()
  expect(screen.getByText('可用')).toBeInTheDocument()
})

test('GWT-98.6 unreachable gateway: health=不可用, frozen 71.3 sentence, local probe rows stay', async () => {
  overview.mockResolvedValue({
    available: false, reason: DUTY_DEGRADE_71_3, empty_state: null,
    degrade_state: DUTY_DEGRADE_71_3,
    models: [], deployments: [], channels: [],
    total: 0, events_24h: 5, latest_batch_verdicts: { spoofed: 1 },
  })
  channels.mockResolvedValue([])
  probes.mockResolvedValue({
    total: 1,
    items: [{
      id: 5, channel_id: 55, model: 'local-spoof', verdict: 'spoofed',
      latency_ms: 90, batch_id: 'batch-local', created_at: NOW, scores: {},
    }],
  })

  renderOps()
  expect(await screen.findByText('不可用')).toBeInTheDocument()
  expect(screen.getByText(DUTY_DEGRADE_71_3)).toBeInTheDocument()
  // 本地探针行继续显示（仅本地事件/探针），不出现第三套网关空态句
  expect(screen.getByText('伪装')).toBeInTheDocument()
  expect(screen.getByText('local-spoof')).toBeInTheDocument()
  expect(screen.queryByText(DUTY_EMPTY_71_2)).not.toBeInTheDocument()
  expect(screen.queryByText(FORBIDDEN_CHANNEL_EMPTY)).not.toBeInTheDocument()
})

test('GWT-98.4 manual probe: in-flight row state, then verdict/latency update from this round', async () => {
  overview.mockResolvedValue({
    available: true, empty_state: null, degrade_state: null,
    models: [], deployments: [], channels: [],
    total: 1, events_24h: 0, latest_batch_verdicts: { original: 1 },
  })
  channels.mockResolvedValue([{
    gateway_ref: 'dep-gpt-4o', model_name: 'gpt-4o',
    effective: { limit_quota: 5000, window_hours: 24, cooldown_seconds: 3600 },
    effective_source: 'channel',
    config: null,
  }])
  probes
    .mockResolvedValueOnce({
      total: 1,
      items: [{
        id: 9, channel_id: 7, model: 'gpt-4o', verdict: 'original', latency_ms: 100,
        batch_id: 'batch-9', created_at: NOW, scores: {},
      }],
    })
    .mockResolvedValue({
      total: 2,
      items: [
        {
          id: 10, channel_id: 7, model: 'gpt-4o', verdict: 'spoofed', latency_ms: 333,
          batch_id: 'manual-t1', created_at: NOW, scores: {},
        },
        {
          id: 9, channel_id: 7, model: 'gpt-4o', verdict: 'original', latency_ms: 100,
          batch_id: 'batch-9', created_at: NOW, scores: {},
        },
      ],
    })

  renderOps()
  fireEvent.click(await screen.findByRole('button', { name: /立即探测/ }))
  expect(trigger).toHaveBeenCalledWith('dep-gpt-4o')
  // 行内「探测中…」+ 按钮加载态；其他区不受锁
  expect(await screen.findByText('探测中…')).toBeInTheDocument()
  expect(screen.getByText('可用')).toBeInTheDocument()
  // 完成后该渠道判定与延迟更新为本轮结果：轮询与页面「刷新」走同一条探针切片数据路径，
  // 测试用「刷新」即时取回 manual 批次行（避免真实 3s 轮询在满载并行下的偶发超时）
  fireEvent.click(screen.getByRole('button', { name: /刷新/ }))
  expect(await screen.findByText('伪装')).toBeInTheDocument()
  expect(screen.getByText('333 ms')).toBeInTheDocument()
  await waitFor(() => {
    expect(screen.getByRole('button', { name: /立即探测/ })).toBeInTheDocument()
  })
})

test('GWT-98.5 clicking a top event row switches to the events tab and highlights the row', async () => {
  overview.mockResolvedValue({
    available: true, empty_state: null, degrade_state: null,
    models: [], deployments: [], channels: [],
    total: 1, events_24h: 1, latest_batch_verdicts: {},
  })
  channels.mockResolvedValue([])
  events.mockResolvedValue({
    total: 1,
    items: [{
      id: 42, channel_id: 7, action: 'disabled', reason: '窗口超限测试',
      source: 'scheduler', created_at: NOW,
    }],
  })

  renderOps()
  // 总览 Top N 行点击（原因文本在总览行 + 事件 tab 行两处，取总览处）
  const topCell = await screen.findAllByText('窗口超限测试')
  fireEvent.click(topCell[0])
  expect(screen.getByRole('tab', { name: /事件/ })).toHaveAttribute('aria-selected', 'true')
  // 事件 tab 该行可见并高亮（events-row-highlight）
  const highlighted = await waitFor(() => {
    const row = document.querySelector('tr.events-row-highlight') as HTMLElement | null
    expect(row).not.toBeNull()
    return row
  })
  expect(highlighted).toHaveTextContent('窗口超限测试')
  // 总览 pane 隐藏（切换只动内容区）
  expect(screen.getByText('近 24h 事件数')).not.toBeVisible()
})

test('GWT-61.1 spoofed latest batch is visible on the duty page; channel stays usable (no auto-disable)', async () => {
  overview.mockResolvedValue({
    available: true, empty_state: null, degrade_state: null,
    models: [], deployments: [], channels: [],
    total: 1, events_24h: 1,
    latest_batch_id: 'batch-spoof',
    latest_batch_verdicts: { spoofed: 1, original: 0, offline: 0 },
  })
  channels.mockResolvedValue([{
    gateway_ref: 'dep-gpt-4o', model_name: 'gpt-4o',
    api_base: 'https://upstream.test/v1', api_key_masked: 'sk***x',
    effective: { limit_quota: 5000, window_hours: 24, cooldown_seconds: 3600 },
    effective_source: 'channel',
    config: null,
  }])
  probes.mockResolvedValue({
    total: 1,
    items: [{
      id: 31, channel_id: 7, model: 'gpt-4o', verdict: 'spoofed', latency_ms: 210,
      batch_id: 'batch-spoof', created_at: NOW, scores: {},
    }],
  })

  renderOps()
  // 总览 Q2：渠道行「伪装」Tag 可见 + 最新批次计数徽标「伪装: 1」（T-32 已落，此处验收）
  expect(await screen.findByText('gpt-4o')).toBeInTheDocument()
  expect(screen.getByText('伪装')).toBeInTheDocument()
  expect(screen.getByText('伪装: 1')).toBeInTheDocument()
  // 渠道保持可用（探针判伪装不自动关）：无「已禁用」态，操作列是值班动作而非关闭渠道
  expect(screen.queryByText('自动禁用')).not.toBeInTheDocument()
  expect(screen.queryByText('人工禁用')).not.toBeInTheDocument()
  const channelsRegion = screen.getByTestId('overview-3q-channels')
  expect(within(channelsRegion).queryByRole('button', { name: /禁\s*用/ })).toBeNull()
  expect(within(channelsRegion).getAllByRole('button', { name: /立即探测/ }).length).toBeGreaterThan(0)

  // 探针 tab：最新批次行内「伪装」可见 + 计数徽标（T-11 补）
  fireEvent.click(screen.getByRole('tab', { name: /探针/ }))
  const summaryTag = await screen.findByTestId('probe-latest-batch')
  expect(summaryTag).toHaveTextContent(PROBE_SPOOF_SUMMARY(1))
  expect(screen.getByText(PROBE_LATEST_BATCH_LABEL)).toBeInTheDocument()
  const batchCell = screen.getAllByText('batch-spoof').find((el) => el.closest('tr'))
  expect(batchCell).toBeDefined()
  const probeRow = batchCell!.closest('tr') as HTMLElement
  expect(within(probeRow).getByText('伪装')).toBeInTheDocument()
})

test('GWT-61.2 gateway down / unregistered models: only frozen empty sentences, no third empty-state family', async () => {
  overview.mockResolvedValue({
    available: false, reason: DUTY_DEGRADE_71_3, empty_state: null,
    degrade_state: DUTY_DEGRADE_71_3,
    models: [], deployments: [], channels: [],
    total: 0, events_24h: 0, latest_batch_id: null, latest_batch_verdicts: {},
  })
  channels.mockResolvedValue([])
  probes.mockResolvedValue({ total: 0, items: [] })
  events.mockResolvedValue({ total: 0, items: [] })

  renderOps()
  // 只出现已冻 71.3 句（71.2 不出现）；第三问空态走已冻 EVENTS_24H_EMPTY
  expect(await screen.findByText(DUTY_DEGRADE_71_3)).toBeInTheDocument()
  expect(screen.queryByText(DUTY_EMPTY_71_2)).not.toBeInTheDocument()
  expect(screen.getByText(EVENTS_24H_EMPTY)).toBeInTheDocument()
  // 无第三套空态句：禁句「暂无渠道」+ 组件默认「暂无数据」都不出现
  expect(screen.queryByText(FORBIDDEN_CHANNEL_EMPTY)).not.toBeInTheDocument()
  expect(screen.queryByText('暂无数据')).not.toBeInTheDocument()

  // 探针 tab：本地探针空 → 已冻 DUTY_LOCAL_PROBE_EMPTY；无批次 → 计数徽标不渲染；仍无第三套
  fireEvent.click(screen.getByRole('tab', { name: /探针/ }))
  expect((await screen.findAllByText(DUTY_LOCAL_PROBE_EMPTY)).length).toBeGreaterThanOrEqual(2)
  expect(screen.queryByTestId('probe-latest-batch')).not.toBeInTheDocument()
  expect(screen.queryByText('暂无数据')).not.toBeInTheDocument()
  expect(screen.queryByText(FORBIDDEN_CHANNEL_EMPTY)).not.toBeInTheDocument()
})
