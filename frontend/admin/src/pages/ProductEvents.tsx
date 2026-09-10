/**
 * 超管产品事实查询页（GWT-15.*）。挂在平台运营台 Tab，租户导航无入口。
 */
import React, { useCallback, useEffect, useState } from 'react'
import { Button, Form, Input, InputNumber, Space, Table, Typography, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { listProductEvents, type ProductEventRow } from '../services/productEvents'
import { apiErrorMessage } from '../utils/errorMessage'

const { Text } = Typography

const ProductEvents: React.FC = () => {
  const [rows, setRows] = useState<ProductEventRow[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [eventName, setEventName] = useState<string>()
  const [tenantId, setTenantId] = useState<number>()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await listProductEvents({
        event_name: eventName || undefined,
        tenant_id: tenantId,
      })
      setRows(data.items)
      setTotal(data.total)
    } catch (e) {
      setRows([])
      setTotal(0)
      message.error(apiErrorMessage(e, '产品事实加载失败'))
    } finally {
      setLoading(false)
    }
  }, [eventName, tenantId])

  useEffect(() => { load() }, [load])

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
            <Button type="primary" onClick={load}>查询</Button>
            <Text type="secondary">共 {total} 条</Text>
          </Space>
        </Form.Item>
      </Form>
      <Table
        rowKey="id"
        size="middle"
        loading={loading}
        columns={columns}
        dataSource={rows}
        pagination={false}
      />
    </div>
  )
}

export default ProductEvents
