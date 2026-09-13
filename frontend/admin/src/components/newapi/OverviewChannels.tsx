/**
 * 三问驾驶舱 · 第二问「真不真、稳不稳」（T-32 / GWT-98.2/98.3）：渠道行 =
 * 网关渠道（/newapi/channels）∪ 本地最新探针行（/newapi/probe-results 切片）合并；
 * 每行 = 渠道名 + 最新判定徽标 + 延迟 + 24h 事件数 + 窗口用量 + 既有配置动作。
 * 判定为伪装（spoofed）/离线（offline）的行排在正常（original）行之前（GWT-98.3），
 * 两组内部按判定时间倒序。T-33：每行「立即探测」入口（仅总览；探测中行内状态）。
 */
import React from 'react'
import { Badge, Button, Space, Table, Tag, Tooltip, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { SettingOutlined } from '@ant-design/icons'
import type {
  ChannelProbeResultItem, GatewayModelWithConfig,
} from '../../services/newapi'
import {
  CELL_UNAVAILABLE, CHANNELS_3Q_LOAD_FAILED, DUTY_LIVE, DUTY_LOCAL_PROBE_EMPTY,
  NO_BUDGET_WINDOW, PROBE_ACTION, PROBING_TEXT, USED_QUOTA_SOURCE_HINT,
  VERDICT_TAG, fmtLatency, fmtQuota, showDutyLiveRow,
} from './newapiShared'
import { LoadEmpty, LoadFailure } from '../LoadState'

const { Text } = Typography

/** 驾驶舱渠道行（Overview3q 装配；判定/延迟取该渠道最新一条探针记录） */
export interface ChannelRow {
  key: string
  model: string
  gatewayRef: string | null
  channelId: number | null
  probe: ChannelProbeResultItem | null
  events24h: number | null
  /** 最近一次事件记录的窗口用量快照（无事件 → null，显示「—」不编 0） */
  usedQuota: number | null
  /** 窗口额度（effective.limit_quota；未纳管 → null） */
  limitQuota: number | null
  /** 网关侧渠道行（含配置动作/上游地址/密钥；仅本地探针行时为 null） */
  channel?: GatewayModelWithConfig | null
  /** T-26 overview.models 行态；缺省回落本地派生 */
  dutyRowStatus?: string | null
  dutyRowStatusText?: string | null
}

interface OverviewChannelsProps {
  rows: ChannelRow[]
  loading: boolean
  failed: boolean
  onRetry: () => void
  onOpenConfig: (record: GatewayModelWithConfig) => void
  /** 行 key → 在飞批次 id（GWT-98.4 行内「探测中…」+ 按钮加载态） */
  probing: Record<string, string>
  onProbe: (row: ChannelRow) => void
  /** 网关可达才允许行标「活」；降级禁止（屏 19） */
  gatewayAvailable: boolean
}

/** GWT-98.3：伪装/离线组在前（组内判定时间倒序），其余在后 */
const problemRank = (row: ChannelRow): number =>
  row.probe && (row.probe.verdict === 'spoofed' || row.probe.verdict === 'offline') ? 0 : 1

const verdictTime = (row: ChannelRow): number => {
  const raw = row.probe?.created_at
  const parsed = raw ? Date.parse(raw) : 0
  return Number.isNaN(parsed) ? 0 : parsed
}

export const sortChannelRows = (rows: ChannelRow[]): ChannelRow[] =>
  [...rows].sort(
    (a, b) =>
      problemRank(a) - problemRank(b) ||
      verdictTime(b) - verdictTime(a) ||
      a.model.localeCompare(b.model),
  )

const OverviewChannels: React.FC<OverviewChannelsProps> = ({
  rows, loading, failed, onRetry, onOpenConfig, probing, onProbe, gatewayAvailable,
}) => {
  if (failed) {
    return <LoadFailure title={CHANNELS_3Q_LOAD_FAILED} onRetry={onRetry} />
  }
  if (loading) {
    return <Table loading rowKey="key" columns={[]} dataSource={[]} pagination={false} />
  }
  if (rows.length === 0) {
    // 已冻句：渠道/探针记录 0（禁止「暂无渠道」第三套）
    return <LoadEmpty title={DUTY_LOCAL_PROBE_EMPTY} />
  }

  const columns: ColumnsType<ChannelRow> = [
    {
      title: '模型/部署', dataIndex: 'model', key: 'model', width: 180,
      render: (v: string) => <Text strong>{v || '-'}</Text>,
    },
    {
      title: '状态', key: 'dutyStatus', width: 72,
      render: (_, row) => {
        const live = showDutyLiveRow({
          dutyRowStatus: row.dutyRowStatus,
          dutyRowStatusText: row.dutyRowStatusText,
          gatewayAvailable,
          registered: Boolean(row.channel),
          verdict: row.probe?.verdict,
        })
        if (!live) return '—'
        const text = row.dutyRowStatusText || DUTY_LIVE
        return (
          <span data-testid="duty-live" aria-label={text}>
            <Badge status="success" text={text} />
          </span>
        )
      },
    },
    {
      title: '最新判定', key: 'verdict', width: 100,
      render: (_, row) => {
        if (!row.probe) return '—'
        const meta = VERDICT_TAG[row.probe.verdict] || { color: 'default', text: row.probe.verdict }
        return <Tag color={meta.color}>{meta.text}</Tag>
      },
    },
    {
      title: '延迟', key: 'latency', width: 100, align: 'right',
      render: (_, row) => (
        // 边界：离线渠道延迟显示「—」，不显示 0ms
        row.probe && row.probe.verdict !== 'offline'
          ? fmtLatency(row.probe.latency_ms)
          : '—'
      ),
    },
    {
      title: '24h 事件', key: 'events24h', width: 90, align: 'right',
      render: (_, row) => (row.events24h === null ? '—' : row.events24h),
    },
    {
      title: '窗口用量', key: 'budget', width: 150,
      render: (_, row) => {
        if (row.limitQuota === null) {
          return (
            <Tooltip title={NO_BUDGET_WINDOW}>
              <span>—</span>
            </Tooltip>
          )
        }
        const used = row.usedQuota === null
          ? (
            <Tooltip title={CELL_UNAVAILABLE}>
              <span>—</span>
            </Tooltip>
          )
          : (
            <Tooltip title={USED_QUOTA_SOURCE_HINT}>
              <span>{fmtQuota(row.usedQuota)}</span>
            </Tooltip>
          )
        return (
          <Space size={2}>
            {used}
            <Text type="secondary">/</Text>
            <span>{fmtQuota(row.limitQuota)}</span>
          </Space>
        )
      },
    },
    {
      title: '引用', dataIndex: 'gatewayRef', key: 'gatewayRef', width: 160, ellipsis: true,
      render: (v: string | null) => (v ? <Text code style={{ fontSize: 12 }}>{v}</Text> : '—'),
    },
    {
      title: '上游地址', key: 'apiBase', ellipsis: true,
      render: (_, row) => row.channel?.api_base || '—',
    },
    {
      title: '密钥', key: 'apiKey', width: 110,
      render: (_, row) =>
        row.channel?.api_key_masked ? <Text code>{row.channel.api_key_masked}</Text> : '—',
    },
    {
      title: '额度调度', key: 'quotaCfg', width: 150,
      render: (_, row) => {
        const record = row.channel
        if (!record) return '—'
        const sourceMeta: Record<string, { color: string; text: string }> = {
          channel: { color: 'blue', text: '模型级' },
          global: { color: 'cyan', text: '全局默认' },
          none: { color: 'default', text: '未纳管' },
        }
        const meta = sourceMeta[record.effective_source] || sourceMeta.none
        return (
          <Space size={4}>
            <Tooltip title={`窗口 ${record.effective.window_hours}h / 冷却 ${record.effective.cooldown_seconds}s`}>
              <Tag color={meta.color}>
                {record.effective_source === 'none' ? '未纳管' : fmtQuota(record.effective.limit_quota)}
              </Tag>
            </Tooltip>
            <Button type="link" size="small" icon={<SettingOutlined />} onClick={() => onOpenConfig(record)}>
              配置
            </Button>
          </Space>
        )
      },
    },
    {
      title: '操作', key: 'probeAction', width: 110,
      render: (_, row) => {
        const busy = row.key in probing
        return (
          <Button size="small" loading={busy} disabled={!row.gatewayRef} onClick={() => onProbe(row)}>
            {busy ? PROBING_TEXT : PROBE_ACTION}
          </Button>
        )
      },
    },
  ]

  return (
    <Table
      size="small"
      columns={columns}
      dataSource={sortChannelRows(rows)}
      rowKey="key"
      pagination={false}
      scroll={{ x: 1100 }}
    />
  )
}

export default OverviewChannels
