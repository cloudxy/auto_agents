/**
 * 超管产品事实查询页（GWT-15.*）。挂在平台运营台 Tab，租户导航无入口。
 * T-23 / FR-84 句族：加载失败 = 「产品事实加载失败。检查网络后重试。」+ 重试（有旧数据句置顶旧表保留），
 * 不空表冒充无事件；真 0 = 「还没有产品事实。…」（edge-states 钉句）。
 */
import React, { useState } from 'react'
import { Button, Form, Input, InputNumber, Space, Table, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { listProductEvents, type ProductEventRow } from '../services/productEvents'
import { LoadEmpty, LoadFailure } from '../components/LoadState'

const { Text } = Typography

const EVENTS_LOAD_FAILED = '产品事实加载失败。检查网络后重试。'
const EVENTS_EMPTY = '还没有产品事实。访客浏览或租户完成动作后会出现在这里。'

interface EventFilters {
  event_name?: string
  tenant_id?: number
}

const ProductEvents: React.FC = () => {
  // 查询面（T-17 Data 同款）：输入为草稿，点「查询」才提交到 applied（查询键）；
  // 同键重点也真拉一次（invalidate 保持按钮语义）。
  const [eventName, setEventName] = useState<string>()
  const [tenantId, setTenantId] = useState<number>()
  const [applied, setApplied] = useState<EventFilters>({})
  const queryClient = useQueryClient()

  const eventsQuery = useQuery({
    queryKey: ['product-events', applied],
    queryFn: () => listProductEvents(applied),
    placeholderData: (prev) => prev,
  })
  const rows = eventsQuery.data?.items || []

  const onSearch = () => {
    setApplied({
      event_name: eventName || undefined,
      tenant_id: typeof tenantId === 'number' ? tenantId : undefined,
    })
    queryClient.invalidateQueries({ queryKey: ['product-events'] })
  }

  const columns: ColumnsType<ProductEventRow> = [
    { title: '发生时间', dataIndex: 'occurred_at', width: 200 },
    { title: '事件', dataIndex: 'event_name', width: 220 },
    { title: '企业', dataIndex: 'tenant_id', width: 80, render: (v) => v ?? '-' },
    { title: '匿名身份', dataIndex: 'anonymous_id', width: 160, render: (v) => v ?? '-' },
    {
      title: '属性', dataIndex: 'props',
      render: (v: Record<string, unknown> | null) => (
        <Text code>{v ? JSON.stringify(v) : '-'}</Text>
      ),
    },
  ]

  return (
    <div>
      <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
        按发生时间查询产品事实（UTC 存储，报表日 Asia/Shanghai）。仅平台超管。
      </Text>
      <Form layout="inline" style={{ marginBottom: 12 }}>
        <Form.Item label="事件名">
          <Input
            allowClear
            placeholder="如 market_subscribe_succeeded"
            value={eventName}
            onChange={(e) => setEventName(e.target.value || undefined)}
            style={{ width: 220 }}
          />
        </Form.Item>
        <Form.Item label="企业 ID">
          <InputNumber
            min={1}
            value={tenantId}
            onChange={(v) => setTenantId(typeof v === 'number' ? v : undefined)}
          />
        </Form.Item>
        <Form.Item>
          <Space>
            <Button type="primary" onClick={onSearch}>查询</Button>
            {/* 失败不得画成「共 0 条」（GWT-84 家族）：仅成功有数据时显示件数 */}
            {eventsQuery.data && <Text type="secondary">共 {eventsQuery.data.total} 条</Text>}
          </Space>
        </Form.Item>
      </Form>
      {/* GWT-84 句族：失败=失败句+重试（无旧数据整表替换，有旧数据句置顶旧表保留）；真 0=「还没有…」 */}
      {eventsQuery.isError && rows.length === 0 ? (
        <LoadFailure title={EVENTS_LOAD_FAILED} onRetry={() => eventsQuery.refetch()} />
      ) : (
        <>
          {eventsQuery.isError && (
            <LoadFailure
              style={{ marginBottom: 12 }}
              title={EVENTS_LOAD_FAILED}
              onRetry={() => eventsQuery.refetch()}
            />
          )}
          <Table
            rowKey="id"
            size="middle"
            loading={eventsQuery.isPending}
            columns={columns}
            dataSource={rows}
            pagination={false}
            locale={{ emptyText: <LoadEmpty title={EVENTS_EMPTY} /> }}
          />
        </>
      )}
    </div>
  )
}

export default ProductEvents
