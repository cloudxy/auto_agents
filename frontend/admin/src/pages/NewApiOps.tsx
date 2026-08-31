/**
 * 中转站管控页（阶段三）- new-api 渠道健康只读视图
 *
 * 三个区块（Tabs，手动刷新、不轮询）：
 * - 渠道总览：远程渠道列表（available=false 时降级 Alert，本地统计仍展示）+
 *   统计行（渠道数 / 近 24h 事件数 / 最近探针批次 verdict 概览）
 * - 探针结果：verdict 分布 + 分页表（scores 可展开），支持渠道 ID 过滤
 * - 事件时间线：调度启停事件分页表，支持渠道 ID 过滤
 *
 * 约定：全只读无写操作；状态 Tag 颜色对齐 new-api 语义（1 绿 / 2 橙 / 3 红 / 未知灰）。
 */
import React, { useCallback, useEffect, useState } from 'react'
import {
  Alert, Button, Card, Form, Input, InputNumber, Modal, Popconfirm, Space, Statistic,
  Table, Tabs, Tag, Tooltip, Typography, message,
} from 'antd'
import { ReloadOutlined, SettingOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  CHANNEL_STATUS, clearChannelConfig, fetchChannelsWithConfig, fetchNewapiEvents,
  fetchNewapiOverview, fetchNewapiProbeResults, setChannelConfig,
} from '../services/newapi'
import type {
  ChannelEventItem, ChannelProbeResultItem, ChannelWithConfig, NewapiOverview, ProbeVerdict,
} from '../services/newapi'

const { Text } = Typography

/** 渠道状态 Tag 映射（1 绿 启用 / 2 橙 人工禁用 / 3 红 自动禁用 / 未知灰） */
const STATUS_TAG: Record<number, { color: string; text: string }> = {
  [CHANNEL_STATUS.ENABLED]: { color: 'green', text: '启用' },
  [CHANNEL_STATUS.MANUALLY_DISABLED]: { color: 'orange', text: '人工禁用' },
  [CHANNEL_STATUS.AUTO_DISABLED]: { color: 'red', text: '自动禁用' },
}

/** 常见渠道类型名（new-api 常量，未收录的展示 type 数字） */
const CHANNEL_TYPE_NAMES: Record<number, string> = {
  1: 'OpenAI',
  14: 'Anthropic',
  24: 'Gemini',
}

/** verdict Tag 映射（original 绿 / spoofed 红 / offline 灰） */
const VERDICT_TAG: Record<ProbeVerdict, { color: string; text: string }> = {
  original: { color: 'green', text: 'original 正品' },
  spoofed: { color: 'red', text: 'spoofed 伪装' },
  offline: { color: 'default', text: 'offline 不可用' },
}

/** 动作 Tag 映射 */
const ACTION_TAG: Record<string, { color: string; text: string }> = {
  disabled: { color: 'red', text: '下线' },
  enabled: { color: 'green', text: '上线' },
}

const fmtTime = (v?: string | null): string => {
  if (!v) return '-'
  const d = new Date(v)
  return Number.isNaN(d.getTime()) ? v : d.toLocaleString('zh-CN', { hour12: false })
}

const fmtQuota = (v?: number | null): string =>
  v === null || v === undefined ? '-' : Number(v).toLocaleString('zh-CN')

const fmtMoney = (v?: number | null): string =>
  v === null || v === undefined ? '-' : `$${Number(v).toFixed(2)}`

const fmtLatency = (v?: number | null): string =>
  v === null || v === undefined || v < 0 ? '-' : `${v} ms`

const DEFAULT_PAGE_SIZE = 10

const NewApiOps: React.FC = () => {
  // ---------------- 总览 ----------------
  const [overview, setOverview] = useState<NewapiOverview | null>(null)
  const [overviewLoading, setOverviewLoading] = useState(false)

  const loadOverview = useCallback(async (showSpin = true) => {
    if (showSpin) setOverviewLoading(true)
    try {
      setOverview(await fetchNewapiOverview())
    } catch (error) {
      message.error('获取中转站总览失败')
    } finally {
      if (showSpin) setOverviewLoading(false)
    }
  }, [])

  // ---------------- 渠道额度配置（4.2 接线） ----------------
  const [channelsCfg, setChannelsCfg] = useState<ChannelWithConfig[]>([])
  const [channelsCfgLoading, setChannelsCfgLoading] = useState(false)
  const [cfgTarget, setCfgTarget] = useState<ChannelWithConfig | null>(null)
  const [cfgSaving, setCfgSaving] = useState(false)
  const [cfgForm] = Form.useForm()

  const loadChannelsCfg = useCallback(async (showSpin = true) => {
    if (showSpin) setChannelsCfgLoading(true)
    try {
      setChannelsCfg(await fetchChannelsWithConfig())
    } catch (error) {
      // 管理面不可达：保持列表为空（顶部已有降级 Alert 说明）
      setChannelsCfg([])
    } finally {
      if (showSpin) setChannelsCfgLoading(false)
    }
  }, [])

  const openCfg = (record: ChannelWithConfig) => {
    setCfgTarget(record)
    cfgForm.setFieldsValue({
      limit_quota: record.effective.limit_quota,
      window_hours: record.effective.window_hours,
      cooldown_seconds: record.effective.cooldown_seconds,
    })
  }

  const onSaveCfg = async () => {
    if (!cfgTarget) return
    try {
      const values = await cfgForm.validateFields()
      setCfgSaving(true)
      await setChannelConfig(cfgTarget.id, values)
      message.success(`渠道 #${cfgTarget.id} 额度配置已保存（调度器下一轮巡检生效）`)
      setCfgTarget(null)
      loadChannelsCfg(false)
      loadEvents(false) // config_updated 事件已落库
    } catch (error) {
      if ((error as { errorFields?: unknown })?.errorFields) return
      message.error('保存渠道配置失败')
    } finally {
      setCfgSaving(false)
    }
  }

  const onClearCfg = async () => {
    if (!cfgTarget) return
    try {
      setCfgSaving(true)
      await clearChannelConfig(cfgTarget.id)
      message.success(`渠道 #${cfgTarget.id} 已清除渠道级配置（回退全局默认）`)
      setCfgTarget(null)
      loadChannelsCfg(false)
      loadEvents(false)
    } catch (error) {
      message.error('清除渠道配置失败')
    } finally {
      setCfgSaving(false)
    }
  }

  // ---------------- 事件时间线 ----------------
  const [events, setEvents] = useState<ChannelEventItem[]>([])
  const [eventsTotal, setEventsTotal] = useState(0)
  const [eventsPage, setEventsPage] = useState(1)
  const [eventsPageSize, setEventsPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [eventsChannelId, setEventsChannelId] = useState<number | undefined>(undefined)
  const [eventsLoading, setEventsLoading] = useState(false)

  const loadEvents = useCallback(async (showSpin = true) => {
    if (showSpin) setEventsLoading(true)
    try {
      const data = await fetchNewapiEvents({
        page: eventsPage,
        page_size: eventsPageSize,
        channel_id: eventsChannelId,
      })
      setEvents(data.items || [])
      setEventsTotal(data.total || 0)
    } catch (error) {
      message.error('获取渠道事件失败')
    } finally {
      if (showSpin) setEventsLoading(false)
    }
  }, [eventsPage, eventsPageSize, eventsChannelId])

  // ---------------- 探针结果 ----------------
  const [probes, setProbes] = useState<ChannelProbeResultItem[]>([])
  const [probesTotal, setProbesTotal] = useState(0)
  const [probesPage, setProbesPage] = useState(1)
  const [probesPageSize, setProbesPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [probesChannelId, setProbesChannelId] = useState<number | undefined>(undefined)
  const [probesLoading, setProbesLoading] = useState(false)

  const loadProbes = useCallback(async (showSpin = true) => {
    if (showSpin) setProbesLoading(true)
    try {
      const data = await fetchNewapiProbeResults({
        page: probesPage,
        page_size: probesPageSize,
        channel_id: probesChannelId,
      })
      setProbes(data.items || [])
      setProbesTotal(data.total || 0)
    } catch (error) {
      message.error('获取探针结果失败')
    } finally {
      if (showSpin) setProbesLoading(false)
    }
  }, [probesPage, probesPageSize, probesChannelId])

  useEffect(() => {
    loadOverview()
    loadChannelsCfg()
  }, [loadOverview, loadChannelsCfg])

  useEffect(() => {
    loadEvents()
  }, [loadEvents])

  useEffect(() => {
    loadProbes()
  }, [loadProbes])

  const refreshAll = () => {
    loadOverview(false)
    loadChannelsCfg(false)
    loadEvents(false)
    loadProbes(false)
  }

  /** 渠道 ID 过滤输入解析（非正整数视为清空过滤） */
  const parseChannelId = (raw: string): number | undefined => {
    const n = Number(raw.trim())
    return raw.trim() && Number.isInteger(n) && n > 0 ? n : undefined
  }

  // ---------------- 表格列 ----------------
  const channelColumns: ColumnsType<ChannelWithConfig> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 70 },
    {
      title: '名称', dataIndex: 'name', key: 'name', width: 160,
      render: (v: string) => <Text strong>{v || '-'}</Text>,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 110,
      render: (v: number) => {
        const meta = STATUS_TAG[v] || { color: 'default', text: `未知(${v})` }
        return <Tag color={meta.color}>{meta.text}</Tag>
      },
    },
    {
      title: '类型', dataIndex: 'type', key: 'type', width: 110,
      render: (v: number) =>
        CHANNEL_TYPE_NAMES[v] ? (
          <Tag color="blue">{CHANNEL_TYPE_NAMES[v]}</Tag>
        ) : (
          <Text type="secondary">type {v}</Text>
        ),
    },
    {
      title: '已用额度', dataIndex: 'used_quota', key: 'used_quota', width: 110, align: 'right',
      render: (v: number | null | undefined) => <Text code>{fmtQuota(v)}</Text>,
    },
    {
      title: '余额', dataIndex: 'balance', key: 'balance', width: 100, align: 'right',
      render: (v: number | null | undefined) => fmtMoney(v),
    },
    {
      title: '响应时间', dataIndex: 'response_time', key: 'response_time', width: 100, align: 'right',
      render: (v: number | null | undefined) => {
        if (v === null || v === undefined) return '-'
        return v < 0 ? (
          <Tooltip title="未测速"><Text type="secondary">未测</Text></Tooltip>
        ) : (
          <span>{fmtLatency(v)}</span>
        )
      },
    },
    {
      title: '模型', dataIndex: 'models', key: 'models', ellipsis: true,
      render: (v: string | null) => (v ? <Text code style={{ fontSize: 12 }}>{v}</Text> : '-'),
    },
    {
      title: '分组', dataIndex: 'group', key: 'group', width: 100,
      render: (v: string | null) => v || '-',
    },
    {
      title: '创建时间', dataIndex: 'created_time', key: 'created_time', width: 170,
      render: (v: number | null | undefined) =>
        v ? new Date(v * 1000).toLocaleString('zh-CN', { hour12: false }) : '-',
    },
    {
      // 4.2 额度调度配置：生效额度（渠道级 > 全局默认）+ 来源标识 + 配置入口
      title: '额度调度', key: 'quota_cfg', width: 190,
      render: (_: unknown, record: ChannelWithConfig) => {
        const sourceMeta: Record<string, { color: string; text: string }> = {
          channel: { color: 'blue', text: '渠道级' },
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
            <Button type="link" size="small" icon={<SettingOutlined />} onClick={() => openCfg(record)}>
              配置
            </Button>
          </Space>
        )
      },
    },
  ]

  const probeColumns: ColumnsType<ChannelProbeResultItem> = [
    {
      title: '时间', dataIndex: 'created_at', key: 'created_at', width: 170,
      render: (v: string | null) => fmtTime(v),
    },
    { title: '渠道 ID', dataIndex: 'channel_id', key: 'channel_id', width: 90 },
    {
      title: '模型', dataIndex: 'model', key: 'model', width: 180, ellipsis: true,
      render: (v: string) => <Text code style={{ fontSize: 12 }}>{v}</Text>,
    },
    {
      title: '判定', dataIndex: 'verdict', key: 'verdict', width: 140,
      render: (v: ProbeVerdict) => {
        const meta = VERDICT_TAG[v] || { color: 'default', text: v }
        return <Tag color={meta.color}>{meta.text}</Tag>
      },
    },
    {
      title: '延迟', dataIndex: 'latency_ms', key: 'latency_ms', width: 100, align: 'right',
      render: (v: number | null | undefined) => fmtLatency(v),
    },
    {
      title: '批次', dataIndex: 'batch_id', key: 'batch_id', width: 140, ellipsis: true,
      render: (v: string) => <Tooltip title={v}><Text code style={{ fontSize: 12 }}>{v}</Text></Tooltip>,
    },
  ]

  const eventColumns: ColumnsType<ChannelEventItem> = [
    {
      title: '时间', dataIndex: 'created_at', key: 'created_at', width: 170,
      render: (v: string | null) => fmtTime(v),
    },
    { title: '渠道 ID', dataIndex: 'channel_id', key: 'channel_id', width: 90 },
    {
      title: '动作', dataIndex: 'action', key: 'action', width: 90,
      render: (v: string) => {
        const meta = ACTION_TAG[v] || { color: 'default', text: v }
        return <Tag color={meta.color}>{meta.text}</Tag>
      },
    },
    {
      title: '用量', dataIndex: 'usage', key: 'usage', width: 100, align: 'right',
      render: (v: number | null | undefined) => fmtQuota(v),
    },
    {
      title: '上限', dataIndex: 'limit_quota', key: 'limit_quota', width: 100, align: 'right',
      render: (v: number | null | undefined) => fmtQuota(v),
    },
    {
      title: '窗口', dataIndex: 'window_hours', key: 'window_hours', width: 80, align: 'right',
      render: (v: number | null | undefined) => (v ? `${v}h` : '-'),
    },
    {
      title: '原因', dataIndex: 'reason', key: 'reason', ellipsis: true,
      render: (v: string | null) => v || '-',
    },
    {
      title: '来源', dataIndex: 'source', key: 'source', width: 100,
      render: (v: string) => (
        <Tag color={v === 'scheduler' ? 'geekblue' : 'gold'}>{v}</Tag>
      ),
    },
  ]

  /** verdict 概览计数（original 绿 / spoofed 红 / offline 灰） */
  const verdicts = overview?.latest_batch_verdicts || {}

  const renderOverviewTab = () => (
    <>
      {overview && !overview.available && (
        <Alert
          type="warning" showIcon style={{ marginBottom: 16 }}
          title="中转站管理面不可达（已降级，仅展示本地数据）"
          description={`原因：${overview.reason || '未知'}。渠道列表来自 new-api 管理面，恢复后点击「刷新」重试；下方本地统计不受影响。`}
        />
      )}
      <Space size={40} wrap style={{ marginBottom: 16 }}>
        <Statistic title="渠道总数" value={overview?.available ? overview.total : '-'} />
        <Statistic title="近 24h 事件数" value={overview?.events_24h ?? '-'} />
        <div>
          <div style={{ color: 'rgba(0,0,0,0.45)', fontSize: 14, marginBottom: 4 }}>
            最近探针批次{overview?.latest_batch_id ? `（${overview.latest_batch_id.slice(0, 8)}…）` : ''}
          </div>
          <Space size={8} wrap>
            {(['original', 'spoofed', 'offline'] as ProbeVerdict[]).map((v) => (
              <Tag key={v} color={VERDICT_TAG[v].color}>
                {VERDICT_TAG[v].text}: {verdicts[v] ?? 0}
              </Tag>
            ))}
          </Space>
        </div>
      </Space>
      <Table
        columns={channelColumns}
        dataSource={overview?.available ? channelsCfg : []}
        rowKey="id"
        loading={overviewLoading || channelsCfgLoading}
        pagination={false}
        scroll={{ x: 1290 }}
        locale={{
          emptyText: overview && !overview.available
            ? '降级模式：中转站不可达，无渠道数据'
            : '暂无渠道（new-api 侧未配置或拉取为空，请检查 NEWAPI 配置）',
        }}
      />
    </>
  )

  const renderProbeTab = () => (
    <>
      <Space style={{ marginBottom: 16 }} wrap>
        <Text type="secondary">按渠道 ID 过滤：</Text>
        <Input.Search
          placeholder="如 5"
          allowClear
          style={{ width: 180 }}
          onSearch={(v) => {
            setProbesChannelId(parseChannelId(v))
            setProbesPage(1)
          }}
        />
      </Space>
      <Table
        columns={probeColumns}
        dataSource={probes}
        rowKey="id"
        loading={probesLoading}
        scroll={{ x: 900 }}
        expandable={{
          rowExpandable: (record) =>
            !!record.scores && Object.keys(record.scores).length > 0,
          expandedRowRender: (record) => (
            <pre style={{ margin: 0, fontSize: 12, whiteSpace: 'pre-wrap' }}>
              {JSON.stringify(record.scores, null, 2)}
            </pre>
          ),
        }}
        pagination={{
          current: probesPage,
          pageSize: probesPageSize,
          total: probesTotal,
          showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p, ps) => {
            setProbesPage(p)
            setProbesPageSize(ps)
          },
        }}
      />
    </>
  )

  const renderEventsTab = () => (
    <>
      <Space style={{ marginBottom: 16 }} wrap>
        <Text type="secondary">按渠道 ID 过滤：</Text>
        <Input.Search
          placeholder="如 5"
          allowClear
          style={{ width: 180 }}
          onSearch={(v) => {
            setEventsChannelId(parseChannelId(v))
            setEventsPage(1)
          }}
        />
      </Space>
      <Table
        columns={eventColumns}
        dataSource={events}
        rowKey="id"
        loading={eventsLoading}
        scroll={{ x: 900 }}
        pagination={{
          current: eventsPage,
          pageSize: eventsPageSize,
          total: eventsTotal,
          showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p, ps) => {
            setEventsPage(p)
            setEventsPageSize(ps)
          },
        }}
      />
    </>
  )

  return (
    <Card
      title="中转站管控（new-api）"
      extra={
        <Button icon={<ReloadOutlined />} onClick={refreshAll} loading={overviewLoading}>
          刷新
        </Button>
      }
    >
      <Tabs
        defaultActiveKey="overview"
        items={[
          { key: 'overview', label: '渠道总览', children: renderOverviewTab() },
          { key: 'probes', label: '探针结果', children: renderProbeTab() },
          { key: 'events', label: '事件时间线', children: renderEventsTab() },
        ]}
      />

      {/* 渠道额度调度配置（4.2 接线：写入 Redis hash，调度器下一轮巡检生效） */}
      <Modal
        title={`渠道 #${cfgTarget?.id ?? ''} 额度调度配置${cfgTarget ? `（${cfgTarget.name}）` : ''}`}
        open={!!cfgTarget}
        onOk={onSaveCfg}
        onCancel={() => setCfgTarget(null)}
        confirmLoading={cfgSaving}
        okText="保存"
        cancelText="取消"
        destroyOnHidden
      >
        <Alert
          type="info" showIcon style={{ marginBottom: 16 }}
          message="窗口内用量达到上限后渠道自动下线，冷却到期自动恢复；额度设为 0 表示显式关闭该渠道调度。"
        />
        <Form form={cfgForm} layout="vertical">
          <Form.Item
            name="limit_quota" label="窗口用量上限（quota）"
            rules={[{ required: true, message: '请输入额度上限' }]}
            tooltip="new-api quota 单位；0 = 关闭该渠道调度"
          >
            <InputNumber min={0} step={100} style={{ width: '100%' }} placeholder="如 100000" />
          </Form.Item>
          <Form.Item name="window_hours" label="统计窗口（小时）" initialValue={24} rules={[{ required: true }]}>
            <InputNumber min={1} max={720} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="cooldown_seconds" label="超限冷却（秒）" initialValue={3600} rules={[{ required: true }]}>
            <InputNumber min={60} max={604800} step={60} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
        {cfgTarget?.config && (
          <Popconfirm
            title="确认清除该渠道的渠道级配置？"
            description="清除后回退全局默认额度；若无全局默认则该渠道退出调度纳管。"
            okText="清除" okButtonProps={{ danger: true }} onConfirm={onClearCfg}
          >
            <Button danger type="link" style={{ padding: 0 }} disabled={cfgSaving}>
              清除渠道级配置（回退全局默认）
            </Button>
          </Popconfirm>
        )}
      </Modal>
    </Card>
  )
}

export default NewApiOps
