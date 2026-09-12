/**
 * 探针结果 Tab（工单 80 拆分自 NewApiOps.tsx）：分页 + 渠道过滤 + scores 展开
 * T-11（GWT-61.1）：最新批次伪装计数徽标——与 Overview3q 共享查询键 ['newapi','overview']
 * （总览已载时零额外请求）；overview 失败/无批次时静默不渲染，不新增空态句（GWT-61.2）。
 */
import React, { useCallback, useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Input, message, Space, Table, Tag, Tooltip, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  fetchNewapiOverview, fetchNewapiProbeResults,
  type ChannelProbeResultItem, type ProbeVerdict,
} from '../../services/newapi'
import {
  DEFAULT_PAGE_SIZE, DUTY_LOCAL_PROBE_EMPTY, PROBE_LATEST_BATCH_LABEL, PROBE_SPOOF_SUMMARY,
  VERDICT_TAG, fmtLatency, fmtTime, parseChannelId,
} from './newapiShared'

const { Text } = Typography

/** refreshSignal 变化时静默刷新（页面「刷新」按钮联动） */
const ProbeResults: React.FC<{ refreshSignal?: number }> = ({ refreshSignal = 0 }) => {
  const [probes, setProbes] = useState<ChannelProbeResultItem[]>([])
  const [probesTotal, setProbesTotal] = useState(0)
  const [probesPage, setProbesPage] = useState(1)
  const [probesPageSize, setProbesPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [probesChannelId, setProbesChannelId] = useState<number | undefined>(undefined)
  const [probesLoading, setProbesLoading] = useState(false)

  // T-11：最新批次伪装计数（latest_batch_verdicts.spoofed 由后端探针引擎落库口径回传）
  const overviewQuery = useQuery({
    queryKey: ['newapi', 'overview'],
    queryFn: fetchNewapiOverview,
  })
  const latestBatchId = overviewQuery.data?.latest_batch_id ?? null
  const spoofedCount = overviewQuery.data?.latest_batch_verdicts?.spoofed ?? 0

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

  useEffect(() => { loadProbes() }, [loadProbes, refreshSignal])  // eslint-disable-line react-hooks/exhaustive-deps

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

  return (
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
        {latestBatchId && (
          <>
            <Text type="secondary">{PROBE_LATEST_BATCH_LABEL}</Text>
            <Tooltip title={latestBatchId}>
              <Text code style={{ fontSize: 12 }}>{latestBatchId}</Text>
            </Tooltip>
            <Tag data-testid="probe-latest-batch" color={VERDICT_TAG.spoofed.color}>
              {PROBE_SPOOF_SUMMARY(spoofedCount)}
            </Tag>
          </>
        )}
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
        locale={{ emptyText: DUTY_LOCAL_PROBE_EMPTY }}
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
}

export default ProbeResults
