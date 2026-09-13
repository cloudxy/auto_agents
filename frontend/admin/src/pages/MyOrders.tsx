/**
 * 我的订单（T-03 / GWT-50.3 UI 面）：档位名 / 状态中文（pending→待确认收款、paid→已确认）
 * / 金额**元**——直渲染后端 amount_yuan（T-02 读模型），不做分→元心算，不写确认履约句。
 * 真 0 空=「还没有升级申请。」（edge-states 钉句）+ 次链（去用量 / 看定价）；
 * 失败=FR-84 句族 + 可点重试；读面无角色门槛（只读也能看）。挂在用量页「我的订单」Tab。
 */
import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button, Card, Skeleton, Table, Typography } from 'antd'

import { listMyOrders, type OrderRow } from '../services/billing'
import { LoadEmpty, LoadFailure } from '../components/LoadState'

const { Text } = Typography

const ORDER_STATUS_TEXT: Record<string, string> = {
  pending: '待确认收款',
  paid: '已确认',
}

const OFFICIAL_URL = (process.env.REACT_APP_OFFICIAL_URL || 'http://localhost:9113').replace(/\/$/, '')

/** 金额（元）：渲染 amount_yuan；缺字段画「—」，不做分→元换算 */
function amountYuanText(row: OrderRow): string {
  return typeof row.amount_yuan === 'number' ? `${row.amount_yuan.toLocaleString()} 元` : '—'
}

interface MyOrdersProps {
  /** 空态次链「去用量」：页内 Tab 场景切回用量；独立渲染时退化为 /usage 路由链接 */
  onGoUsage?: () => void
}

const MyOrders: React.FC<MyOrdersProps> = ({ onGoUsage }) => {
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
        <LoadEmpty
          title="还没有升级申请。"
          action={
            onGoUsage ? (
              <Button size="small" onClick={onGoUsage}>去用量</Button>
            ) : (
              <Button size="small" href="/usage">去用量</Button>
            )
          }
        />
        <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
          提交线下升级申请后，待确认和已确认都会列在这里。
        </Text>
        <Button type="link" href={`${OFFICIAL_URL}/pricing`} target="_blank" rel="noopener noreferrer">
          看定价
        </Button>
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
          { title: '档位', dataIndex: 'plan_name', render: (v: string | undefined) => v || '—' },
          { title: '状态', dataIndex: 'status', width: 140, render: (v: string) => ORDER_STATUS_TEXT[v] || v },
          { title: '金额', dataIndex: 'amount_yuan', width: 140, render: (_: unknown, row: OrderRow) => amountYuanText(row) },
        ]}
      />
    </Card>
  )
}

export default MyOrders
