/**
 * T-19 待确认收款：结账待支付行；企业名+展示金额；空态「暂无待确认收款」。
 *
 * 审计 BUG-25：同一列表还承接两类「钱到了但权益没开」的单——
 * - 已付款待开通（通道验真通过、履约失败，如套餐被下架）：可「重新开通」；
 * - 订单取消 / 超时后才到账（迟到成功通知）：需人工退款或补单，只做醒目提示。
 */
import React from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Popconfirm, Table, Tag, Tooltip, message } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import {
  CHANNEL_LABEL, confirmOrder, listPendingOrders, retryFulfillment, type OrderRow,
} from '../../services/billing'
import { apiErrorMessage } from '../../utils/errorMessage'
import { LoadEmpty, LoadFailure } from '../LoadState'

const ORDERS_LOAD_FAILED = '待确认收款列表加载失败。检查网络后重试。'
export const ORDERS_EMPTY = '暂无待确认收款'

const PENDING = new Set(['checkout_pending', 'pending'])
const PAID_NOT_FULFILLED = 'paid_pending_fulfillment'

type RowKind = 'pending' | 'paid_not_fulfilled' | 'late_paid'

function kindOf(row: OrderRow): RowKind | null {
  if (PENDING.has(row.status)) return 'pending'
  if (row.status === PAID_NOT_FULFILLED) return 'paid_not_fulfilled'
  if (row.status === 'unpaid' && row.late_notify_at) return 'late_paid'
  return null
}

const KIND_TAG: Record<RowKind, { color: string; label: string }> = {
  pending: { color: 'gold', label: '待收款' },
  paid_not_fulfilled: { color: 'red', label: '已付款待开通' },
  late_paid: { color: 'volcano', label: '关单后到账' },
}

function displayAmount(row: OrderRow): string {
  const yuan = typeof row.amount_yuan === 'number' ? row.amount_yuan : row.amount_cents / 100
  return `¥${yuan.toLocaleString('en-US')}`
}

const PendingOrdersTab: React.FC = () => {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['pending-orders'], queryFn: listPendingOrders, retry: false })
  const rows = (q.data || []).filter((r) => kindOf(r) !== null)

  const refresh = () => { void qc.invalidateQueries({ queryKey: ['pending-orders'] }) }

  const onConfirm = async (row: OrderRow) => {
    try {
      await confirmOrder(row.id)
      message.success('已确认收款')
      refresh()
    } catch (e) {
      message.error(apiErrorMessage(e, '确认失败，订单仍待确认'))
    }
  }

  const onRetry = async (row: OrderRow) => {
    try {
      await retryFulfillment(row.id)
      message.success('已重新开通')
      refresh()
    } catch (e) {
      message.error(apiErrorMessage(e, '开通仍未成功，请检查套餐配置后重试'))
      refresh()
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
        scroll={{ x: 720 }}
        locale={{ emptyText: <LoadEmpty title={ORDERS_EMPTY} /> }}
        columns={[
          { title: '企业', dataIndex: 'tenant_name', render: (v: string | undefined) => v || '—' },
          { title: '商品', dataIndex: 'plan_name', render: (v: string | undefined, r) => v || r.product_code || '—' },
          { title: '金额', key: 'amount', width: 120, render: (_: unknown, r) => displayAmount(r) },
          { title: '通道', dataIndex: 'channel', width: 100, render: (v: string) => CHANNEL_LABEL[v] || v || '线下' },
          {
            title: '状态',
            key: 'kind',
            width: 130,
            render: (_: unknown, r) => {
              const kind = kindOf(r)
              return kind ? <Tag color={KIND_TAG[kind].color}>{KIND_TAG[kind].label}</Tag> : null
            },
          },
          {
            title: '操作',
            width: 160,
            render: (_: unknown, r) => {
              const kind = kindOf(r)
              if (kind === 'paid_not_fulfilled') {
                return (
                  <Popconfirm
                    title="重新为该企业开通权益？"
                    okText="重新开通"
                    cancelText="取消"
                    onConfirm={() => onRetry(r)}
                  >
                    <Button size="small" type="primary" danger>重新开通</Button>
                  </Popconfirm>
                )
              }
              if (kind === 'late_paid') {
                return (
                  <Tooltip title="订单已取消或超时后才收到付款成功通知：请核对到账后人工退款，或让企业重新下单后在此确认收款。">
                    <Tag color="volcano">需人工处理</Tag>
                  </Tooltip>
                )
              }
              return (
                <Popconfirm
                  title="确认已收到该笔款项？此操作不可逆。"
                  okText="确认收款"
                  cancelText="取消"
                  onConfirm={() => onConfirm(r)}
                >
                  <Button size="small" type="primary">确认收款</Button>
                </Popconfirm>
              )
            },
          },
        ]}
      />
    </div>
  )
}

export default PendingOrdersTab
