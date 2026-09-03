/**
 * 探针结果 Tab（工单 80 拆分自 NewApiOps.tsx）：分页 + 渠道过滤 + scores 展开
 */
import React, { useCallback, useEffect, useState } from 'react'
import { Input, message, Space, Table, Tag, Tooltip, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { fetchNewapiProbeResults, type ChannelProbeResultItem, type ProbeVerdict } from '../../services/newapi'
import { DEFAULT_PAGE_SIZE, VERDICT_TAG, fmtLatency, fmtTime, parseChannelId } from './newapiShared'

const { Text } = Typography

/** refreshSignal 变化时静默刷新（页面「刷新」按钮联动） */
const ProbeResults: React.FC<{ refreshSignal?: number }> = ({ refreshSignal = 0 }) => {
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
}

export default ProbeResults
