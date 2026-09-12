/**
 * 总览三问驾驶舱（T-32 / GWT-98.2..98.6，Q-OVERVIEW-3Q 已决）：一屏回答值班三问
 * —— 能不能用 / 真不真稳不稳 / 刚才发生了什么。三区各自独立加载/失败/重试
 * （GWT-98.4 边界：任一接口挂不拖垮全区，失败句走 FR-84 族 LoadState）。
 * 数据面 react-query 化（与 T-17 Dashboard/Data 同款）；网关不可达走已冻 71.3 句，
 * 本地探针/事件继续显示（GWT-98.6，无第三套空态）。
 * T-33：立即探测（行内入口 + accepted 批次条件轮询，react-query refetchInterval，
 * 无手写定时器；探测中不锁其他区）。
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Alert, Button, Card, Empty, Skeleton, Space, Statistic, Table, Tag, Tooltip, Typography, message,
} from 'antd'
import { CheckCircleFilled, CloseCircleFilled } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  fetchChannelsWithConfig, fetchNewapiEvents, fetchNewapiOverview,
  fetchNewapiProbeResults, triggerNewapiProbe,
} from '../../services/newapi'
import type {
  ChannelEventItem, ChannelProbeResultItem, GatewayModelWithConfig, ProbeVerdict,
} from '../../services/newapi'
import { LoadEmpty, LoadFailure } from '../LoadState'
import OverviewChannels, { type ChannelRow } from './OverviewChannels'
import {
  ACTION_TAG, DUTY_DEGRADE_71_3, DUTY_DEGRADE_71_3_HINT,
  DUTY_EMPTY_71_2, DUTY_EMPTY_71_2_HINT, DUTY_LOAD_FAILED, EVENTS_24H_EMPTY,
  EVENTS_3Q_LOAD_FAILED, OFFLINE_LOCAL_HINT, PROBE_DONE, PROBE_TRIGGER_FAILED,
  VERDICT_TAG, channelIdFromRef, fmtTime,
} from './newapiShared'

const { Text } = Typography

/** 切片窗口：探针/事件各取最近 100 条（API page_size 上限）用于「最新判定/24h 计数」 */
const SLICE_SIZE = 100
/** 最近事件 Top N（edge-states：默认 10） */
const TOP_N = 10
const REGION_STYLE: React.CSSProperties = { marginBottom: 16 }
const DAY_MS = 24 * 60 * 60 * 1000

interface Overview3qProps {
  /** Q2 既有「配置」动作（窗口配置 Modal 仍归页面管，GWT-99.3 动作不回退） */
  onOpenConfig: (record: GatewayModelWithConfig) => void
  /** GWT-98.5：最近事件行点击 → 切「事件」tab 并聚焦该行 */
  onJumpToEvent: (eventId: number) => void
}

const Overview3q: React.FC<Overview3qProps> = ({ onOpenConfig, onJumpToEvent }) => {
  const overviewQuery = useQuery({
    queryKey: ['newapi', 'overview'],
    queryFn: fetchNewapiOverview,
  })
  const channelsQuery = useQuery({
    queryKey: ['newapi', 'channels'],
    queryFn: fetchChannelsWithConfig,
  })

  // T-33：行 key → 在飞批次 id；有在飞批次时对探针切片条件轮询（3s）
  const [probingBatches, setProbingBatches] = useState<Record<string, string>>({})
  const probingActive = Object.keys(probingBatches).length > 0
  const probesQuery = useQuery({
    queryKey: ['newapi', 'probe-latest'],
    queryFn: () => fetchNewapiProbeResults({ page: 1, page_size: SLICE_SIZE }),
    refetchInterval: probingActive ? 3000 : false,
  })
  const eventsQuery = useQuery({
    queryKey: ['newapi', 'events-slice'],
    queryFn: () => fetchNewapiEvents({ page: 1, page_size: SLICE_SIZE }),
  })

  const handleProbe = useCallback(async (row: ChannelRow) => {
    if (!row.gatewayRef) return
    try {
      const result = await triggerNewapiProbe(row.gatewayRef)
      if (!result.accepted) {
        message.warning(result.reason || PROBE_TRIGGER_FAILED)
        return
      }
      setProbingBatches((prev) => ({ ...prev, [row.key]: result.batch_id }))
    } catch (error) {
      message.error(PROBE_TRIGGER_FAILED)
    }
  }, [])

  // 完成检测：探针切片出现本批次 id → 清除在飞 + 行内判定/延迟随数据更新（GWT-98.4）
  useEffect(() => {
    const items = probesQuery.data?.items || []
    const finished = Object.entries(probingBatches).filter(
      ([, batchId]) => batchId && items.some((item) => item.batch_id === batchId),
    )
    if (!finished.length) return
    setProbingBatches((prev) => {
      const next = { ...prev }
      finished.forEach(([key]) => { delete next[key] })
      return next
    })
    message.success(PROBE_DONE)
  }, [probesQuery.data, probingBatches])

  /** Q2 行装配：channels ∪ 探针行（按 model_name 关联最新探针；事件按 channel_id 计数） */
  const rows = useMemo<ChannelRow[]>(() => {
    const probes = probesQuery.data?.items || []
    const events = eventsQuery.data?.items || []
    const channels = channelsQuery.data || []

    const latestByModel = new Map<string, ChannelProbeResultItem>()
    for (const item of probes) {
      if (item.model && !latestByModel.has(item.model)) latestByModel.set(item.model, item)
    }
    const cutoff = Date.now() - DAY_MS
    const events24hByChannel = new Map<number, number>()
    const usedByChannel = new Map<number, number>()
    for (const event of events) {
      const ts = event.created_at ? Date.parse(event.created_at) : Number.NaN
      if (!Number.isNaN(ts) && ts >= cutoff) {
        events24hByChannel.set(
          event.channel_id, (events24hByChannel.get(event.channel_id) || 0) + 1,
        )
      }
      if (event.usage !== null && event.usage !== undefined && !usedByChannel.has(event.channel_id)) {
        usedByChannel.set(event.channel_id, event.usage)
      }
    }

    const out: ChannelRow[] = []
    const seenModels = new Set<string>()
    for (const channel of channels) {
      const probe = latestByModel.get(channel.model_name) || null
      // channel_id 关联：探针行自带；无探针记录时仅数值引用可镜像（见 channelIdFromRef）
      const channelId = probe?.channel_id ?? channelIdFromRef(channel.gateway_ref)
      out.push({
        key: `cfg:${channel.gateway_ref}`,
        model: channel.model_name,
        gatewayRef: channel.gateway_ref,
        channelId,
        probe,
        events24h: channelId === null ? null : (events24hByChannel.get(channelId) ?? 0),
        usedQuota: channelId === null ? null : (usedByChannel.get(channelId) ?? null),
        limitQuota: channel.effective_source === 'none' ? null : channel.effective.limit_quota,
        channel,
      })
      seenModels.add(channel.model_name)
    }
    // 网关降级（71.3）时 channels 为空：本地探针行仍显示（「仅本地事件/探针」）
    latestByModel.forEach((probe, model) => {
      if (seenModels.has(model)) return
      out.push({
        key: `probe:${probe.channel_id}`,
        model,
        gatewayRef: null,
        channelId: probe.channel_id,
        probe,
        events24h: events24hByChannel.get(probe.channel_id) ?? 0,
        usedQuota: usedByChannel.get(probe.channel_id) ?? null,
        limitQuota: null,
        channel: null,
      })
    })
    return out
  }, [probesQuery.data, eventsQuery.data, channelsQuery.data])

  const overview = overviewQuery.data
  const offline = typeof navigator !== 'undefined' && !navigator.onLine

  const renderHealth = () => {
    if (overviewQuery.isLoading) return <Skeleton active paragraph={{ rows: 1 }} />
    if (overviewQuery.isError) {
      return <LoadFailure title={DUTY_LOAD_FAILED} onRetry={() => overviewQuery.refetch()} />
    }
    if (!overview) return null
    return (
      <>
        <Space size={32} wrap>
          {overview.available ? (
            <Tag icon={<CheckCircleFilled />} color="success">可用</Tag>
          ) : (
            <Tag icon={<CloseCircleFilled />} color="error">不可用</Tag>
          )}
          <Statistic title="模型/部署" value={overview.available ? overview.total : '-'} />
          <div>
            <div style={{ color: 'rgba(0,0,0,0.45)', fontSize: 14 }}>
              部署 {overview.deployments.length} 个
            </div>
            <Tooltip
              title={overview.deployments.length
                ? overview.deployments.map((d) => d.model_name).join('、')
                : undefined}
            >
              <Text type="secondary" style={{ fontSize: 12 }}>
                {overview.deployments.length
                  ? overview.deployments.slice(0, 3).map((d) => d.model_name).join('、')
                  : '暂无部署'}
              </Text>
            </Tooltip>
          </div>
        </Space>
        {!overview.available && (
          <Alert
            type="warning" showIcon style={{ marginTop: 12 }}
            title={overview.degrade_state || DUTY_DEGRADE_71_3}
            description={DUTY_DEGRADE_71_3_HINT}
          />
        )}
        {overview.available && (overview.total ?? 0) === 0 && (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <span>
                <div>{overview.empty_state || DUTY_EMPTY_71_2}</div>
                <Text type="secondary">{DUTY_EMPTY_71_2_HINT}</Text>
              </span>
            }
          >
            <Button type="primary" onClick={() => {
              overviewQuery.refetch()
              channelsQuery.refetch()
            }}
            >
              刷新
            </Button>
          </Empty>
        )}
      </>
    )
  }

  const verdicts = overview?.latest_batch_verdicts || {}
  const eventColumns: ColumnsType<ChannelEventItem> = [
    {
      title: '时间', dataIndex: 'created_at', key: 'created_at', width: 160,
      render: (v: string | null) => fmtTime(v),
    },
    { title: '渠道 ID', dataIndex: 'channel_id', key: 'channel_id', width: 80 },
    {
      title: '动作', dataIndex: 'action', key: 'action', width: 80,
      render: (v: string) => {
        const meta = ACTION_TAG[v] || { color: 'default', text: v }
        return <Tag color={meta.color}>{meta.text}</Tag>
      },
    },
    {
      title: '原因', dataIndex: 'reason', key: 'reason', ellipsis: true,
      render: (v: string | null) => v || '-',
    },
  ]
  const topEvents = (eventsQuery.data?.items || []).slice(0, TOP_N)

  const renderRecentEvents = () => {
    if (eventsQuery.isLoading) return <Skeleton active paragraph={{ rows: 3 }} />
    if (eventsQuery.isError) {
      return <LoadFailure title={EVENTS_3Q_LOAD_FAILED} onRetry={() => eventsQuery.refetch()} />
    }
    if (topEvents.length === 0) return <LoadEmpty title={EVENTS_24H_EMPTY} />
    return (
      <Table
        size="small"
        columns={eventColumns}
        dataSource={topEvents}
        rowKey="id"
        pagination={false}
        onRow={(record) => ({
          onClick: () => onJumpToEvent(record.id),
          onKeyDown: (e: React.KeyboardEvent) => {
            if (e.key === 'Enter') onJumpToEvent(record.id)
          },
          tabIndex: 0,
          style: { cursor: 'pointer' },
        })}
      />
    )
  }

  return (
    <div data-testid="overview-3q">
      {offline && (
        <Alert type="warning" showIcon style={{ marginBottom: 16 }} title={OFFLINE_LOCAL_HINT} />
      )}
      <Card size="small" title="能不能用" style={REGION_STYLE} data-testid="overview-3q-health">
        {renderHealth()}
      </Card>
      <Card
        size="small"
        title="真不真、稳不稳"
        style={REGION_STYLE}
        data-testid="overview-3q-channels"
        extra={overview ? (
          <Space size={8} wrap>
            <Tooltip title={overview.latest_batch_id ? `批次 ${overview.latest_batch_id.slice(0, 8)}…` : undefined}>
              <Text type="secondary" style={{ fontSize: 12 }}>最近探针批次</Text>
            </Tooltip>
            {(['original', 'spoofed', 'offline'] as ProbeVerdict[]).map((v) => (
              <Tag key={v} color={VERDICT_TAG[v].color}>
                {VERDICT_TAG[v].text}: {verdicts[v] ?? 0}
              </Tag>
            ))}
          </Space>
        ) : null}
      >
        <OverviewChannels
          rows={rows}
          loading={channelsQuery.isLoading || probesQuery.isLoading}
          failed={channelsQuery.isError || probesQuery.isError}
          onRetry={() => { channelsQuery.refetch(); probesQuery.refetch() }}
          onOpenConfig={onOpenConfig}
          probing={probingBatches}
          onProbe={handleProbe}
        />
      </Card>
      <Card
        size="small"
        title="刚才发生了什么"
        style={REGION_STYLE}
        data-testid="overview-3q-events"
        extra={<Statistic title="近 24h 事件数" value={overview?.events_24h ?? '-'} />}
      >
        {renderRecentEvents()}
      </Card>
    </div>
  )
}

export default Overview3q
