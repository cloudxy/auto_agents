/**
 * 平台超管：待确认收款订单。确认后套用套餐配额。
 */
import React from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Popconfirm, Space, Table, Tag, Typography, message } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { CHANNEL_LABEL, confirmOrder, listPendingOrders, type OrderRow } from '../../services/billing'
import { apiErrorMessage } from '../../utils/errorMessage'

const { Text } = Typography

const yuan = (cents: number) => (cents / 100).toFixed(2)

const PendingOrdersTab: React.FC = () => {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['billing-pending-orders'], queryFn: listPendingOrders })
  const rows = q.data ?? []
  const load = () => { void qc.invalidateQueries({ queryKey: ['billing-pending-orders'] }) }

  const onConfirm = async (row: OrderRow) => {
    try {
      await confirmOrder(row.id)
      message.success(`订单 #${row.id} 已确认收款，配额已套用`)
      load()
    } catch (e) {
      message.error(apiErrorMessage(e, '确认失败'))
    }
  }

  return (
    <div>
      {q.isError ? (
        <Alert type="error" showIcon style={{ marginBottom: 12 }}
               title={apiErrorMessage(q.error, '待确认订单加载失败')} />
      ) : null}
      <Alert
        type="info" showIcon style={{ marginBottom: 12 }}
        title="租户在用量页下单后出现在此。确认收款即套用套餐配额（支付宝/微信本环境不直连网关，以人工到账为准）。"
      />
      <Space style={{ marginBottom: 12 }}>
        <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
      </Space>
      <Table<OrderRow>
        rowKey="id" size="small" loading={q.isLoading} dataSource={rows} pagination={false}
        columns={[
          { title: '订单', dataIndex: 'id', width: 70, render: (v: number) => `#${v}` },
          { title: '租户', dataIndex: 'tenant_id', width: 80, render: (v: number | null) => v ?? '-' },
          { title: '金额', dataIndex: 'amount_cents', width: 90, render: (v: number) => `¥${yuan(v)}` },
          { title: '渠道', dataIndex: 'channel', width: 100,
            render: (v: string) => <Text>{CHANNEL_LABEL[v] || v}</Text> },
          { title: '状态', dataIndex: 'status', width: 90, render: () => <Tag color="gold">待确认</Tag> },
          { title: '操作', width: 110, render: (_: unknown, row) => (
            <Popconfirm title={`确认订单 #${row.id} 已到账？`} okText="确认收款" cancelText="取消"
                        onConfirm={() => onConfirm(row)}>
              <Button type="link" size="small">确认收款</Button>
            </Popconfirm>
          ) },
        ]}
        locale={{ emptyText: '没有待确认订单' }}
      />
    </div>
  )
}

export default PendingOrdersTab
