/**
 * 我的订单（T-09）：租户状态闭集仅待支付 / 已开通。不另钉空态金标。
 */
import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button, Card, Skeleton, Table } from 'antd'

import { CHECKOUT_PATH_PRO, PRICING_CTA_CHECKOUT } from '../constants/collectCopy'
import { listMyOrders, type OrderRow } from '../services/billing'
import { LoadFailure } from '../components/LoadState'
import { tenantOrderStatus } from '../utils/orderStatus'

function amountYuanText(row: OrderRow): string {
  return typeof row.amount_yuan === 'number' ? `${row.amount_yuan.toLocaleString()} 元` : '—'
}

interface MyOrdersProps {
  onGoUsage?: () => void
}

const MyOrders: React.FC<MyOrdersProps> = () => {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['my-orders'],
    queryFn: listMyOrders,
  })

  if (isLoading) return <Skeleton active paragraph={{ rows: 4 }} />
  if (isError) {
    return <LoadFailure title="订单列表加载失败。检查网络后重试。" onRetry={() => { void refetch() }} />
  }

  const rows = data || []
  if (rows.length === 0) {
    return (
      <div>
        <Button type="primary" href={CHECKOUT_PATH_PRO}>{PRICING_CTA_CHECKOUT}</Button>
      </div>
    )
  }

  return (
    <Card title="我的订单" size="small">
      <Table<OrderRow>
        rowKey="id"
        size="small"
        pagination={false}
        dataSource={rows}
        columns={[
          { title: '商品', dataIndex: 'plan_name', render: (v: string | undefined, row) => v || row.product_code || '—' },
          { title: '状态', dataIndex: 'status', width: 140, render: (v: string) => tenantOrderStatus(v) },
          { title: '金额', dataIndex: 'amount_yuan', width: 140, render: (_: unknown, row: OrderRow) => amountYuanText(row) },
        ]}
      />
    </Card>
  )
}

export default MyOrders
