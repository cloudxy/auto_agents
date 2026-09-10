/**
 * 事件时间线 Tab（工单 80 拆分自 NewApiOps.tsx）：分页 + 渠道过滤
 */
import React, { useCallback, useEffect, useState } from 'react'
import { Input, message, Space, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { fetchNewapiEvents, type ChannelEventItem } from '../../services/newapi'
import { ACTION_TAG, DEFAULT_PAGE_SIZE, fmtQuota, fmtTime, parseChannelId } from './newapiShared'

const { Text } = Typography

/** refreshSignal 变化时静默刷新；configSaved 保存渠道配置后联动刷新 */
const EventsList: React.FC<{ refreshSignal?: number; configSaved?: number }> = ({ refreshSignal = 0, configSaved = 0 }) => {
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

  useEffect(() => { loadEvents() }, [loadEvents, refreshSignal, configSaved])  // eslint-disable-line react-hooks/exhaustive-deps

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

  return (
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
}

export default EventsList
