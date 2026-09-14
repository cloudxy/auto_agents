/**
 * T-19 待确认收款：结账待支付行；企业名+展示金额；空态「暂无待确认收款」。
 */
import React from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Popconfirm, Table, message } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { CHANNEL_LABEL, confirmOrder, listPendingOrders, type OrderRow } from '../../services/billing'
import { apiErrorMessage } from '../../utils/errorMessage'
import { LoadEmpty, LoadFailure } from '../LoadState'

const ORDERS_LOAD_FAILED = '待确认收款列表加载失败。检查网络后重试。'
export const ORDERS_EMPTY = '暂无待确认收款'

const PENDING = new Set(['checkout_pending', 'pending'])

function displayAmount(row: OrderRow): string {
  const yuan = typeof row.amount_yuan === 'number' ? row.amount_yuan : row.amount_cents / 100
  return `¥${yuan.toLocaleString('en-US')}`
}

const PendingOrdersTab: React.FC = () => {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['pending-orders'], queryFn: listPendingOrders, retry: false })
  const rows = (q.data || []).filter((r) => PENDING.has(r.status))

  const onConfirm = async (row: OrderRow) => {
    try {
      await confirmOrder(row.id)
      message.success('已确认收款')
      void qc.invalidateQueries({ queryKey: ['pending-orders'] })
    } catch (e) {
      message.error(apiErrorMessage(e, '确认失败，订单仍待确认'))
    }
  }

  if (q.isError) {
    return <LoadFailure title={ORDERS_LOAD_FAILED} onRetry={() => { void q.refetch() }} />
  }

  return (
    <div data-testid="pending-orders">
      <Button icon={<ReloadOutlined />} onClick={() => q.refetch()} style={{ marginBottom: 12 }}>刷新</Button>
      <Table<OrderRow>
        rowKey="id"
        size="middle"
        loading={q.isPending}
        dataSource={rows}
        pagination={{ pageSize: 20 }}
        locale={{ emptyText: <LoadEmpty title={ORDERS_EMPTY} /> }}
        columns={[
          { title: '企业', dataIndex: 'tenant_name', render: (v: string | undefined) => v || '—' },
          { title: '商品', dataIndex: 'plan_name', render: (v: string | undefined, r) => v || r.product_code || '—' },
          { title: '金额', key: 'amount', width: 120, render: (_: unknown, r) => displayAmount(r) },
          { title: '通道', dataIndex: 'channel', width: 100, render: (v: string) => CHANNEL_LABEL[v] || v },
          {
            title: '操作',
            width: 120,
            render: (_: unknown, r) => (
              <Popconfirm
                title="确认已收到该笔款项？此操作不可逆。"
                okText="确认收款"
                cancelText="取消"
                onConfirm={() => onConfirm(r)}
              >
                <Button size="small" type="primary">确认收款</Button>
              </Popconfirm>
            ),
          },
        ]}
      />
    </div>
  )
}

export default PendingOrdersTab
