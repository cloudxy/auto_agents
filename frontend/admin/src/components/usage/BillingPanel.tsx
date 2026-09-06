/**
 * 租户订购最小环：选套餐 + 支付宝/微信/线下渠道下单，等待超管确认收款。
 * 本环境不直连支付网关，渠道字段用于对账与运营台确认。
 */
import React, { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Radio, Space, Table, Tag, Typography, message } from 'antd'
import {
  CHANNEL_LABEL, createOrder, fetchSubscription, listMyOrders, listPlans,
  type PayChannel, type PlanRow,
} from '../../services/billing'
import { apiErrorMessage } from '../../utils/errorMessage'

const { Text } = Typography

const yuan = (cents: number) => (cents / 100).toFixed(2)

const BillingPanel: React.FC = () => {
  const qc = useQueryClient()
  const plansQ = useQuery({ queryKey: ['billing-plans'], queryFn: listPlans })
  const subQ = useQuery({ queryKey: ['billing-subscription'], queryFn: fetchSubscription })
  const ordersQ = useQuery({ queryKey: ['billing-orders'], queryFn: listMyOrders })
  const [channel, setChannel] = useState<PayChannel>('alipay')
  const [ordering, setOrdering] = useState<number | null>(null)

  const plans = plansQ.data ?? []
  const orders = ordersQ.data ?? []
  const loadErr = plansQ.isError || ordersQ.isError
    ? apiErrorMessage(plansQ.error ?? ordersQ.error, '订购信息加载失败')
    : null

  const onOrder = async (plan: PlanRow) => {
    try {
      setOrdering(plan.id)
      const order = await createOrder(plan.id, channel)
      message.success(
        `已下单 #${order.id}（${CHANNEL_LABEL[channel]} ¥${yuan(order.amount_cents)}）。到账后由平台超管在运营台确认收款。`,
      )
      await qc.invalidateQueries({ queryKey: ['billing-orders'] })
    } catch (e) {
      message.error(apiErrorMessage(e, '下单失败'))
    } finally {
      setOrdering(null)
    }
  }

  return (
    <Card title="套餐与订购" style={{ marginTop: 16 }} loading={plansQ.isLoading}>
      {loadErr ? <Alert type="error" showIcon style={{ marginBottom: 12 }} title={loadErr} /> : null}
      <Alert
        type="info" showIcon style={{ marginBottom: 12 }}
        title="付费最小环：选渠道下单 → 按订单号完成支付宝/微信/线下转账 → 平台超管确认收款后配额生效。本环境不直连支付网关。"
      />
      {subQ.data ? (
        <Text style={{ display: 'block', marginBottom: 12 }}>
          当前订阅：计划 #{subQ.data.plan_id} · {subQ.data.status}
          {subQ.data.current_period_end
            ? ` · 到期 ${new Date(subQ.data.current_period_end).toLocaleDateString('zh-CN')}`
            : ' · 不过期'}
        </Text>
      ) : (
        <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>尚未挂接付费订阅（注册默认免费档）</Text>
      )}
      <Space style={{ marginBottom: 12 }}>
        <Text>支付渠道：</Text>
        <Radio.Group value={channel} onChange={(e) => setChannel(e.target.value)}
                     options={[
                       { value: 'alipay', label: '支付宝' },
                       { value: 'wechat', label: '微信支付' },
                       { value: 'offline', label: '线下转账' },
                     ]} />
      </Space>
      <Table<PlanRow>
        rowKey="id" size="small" pagination={false} dataSource={plans}
        columns={[
          { title: '套餐', dataIndex: 'name', render: (v: string, r) => <><Text strong>{v}</Text> <Text type="secondary">({r.slug})</Text></> },
          { title: '周期', dataIndex: 'period', width: 80 },
          { title: '价格', dataIndex: 'price_cents', width: 100, render: (v: number) => (v === 0 ? '免费' : `¥${yuan(v)}`) },
          { title: '操作', width: 100, render: (_: unknown, plan) => (
            <Button type="link" size="small" disabled={plan.price_cents === 0}
                    loading={ordering === plan.id} onClick={() => onOrder(plan)}>下单</Button>
          ) },
        ]}
        locale={{ emptyText: '暂无公开套餐' }}
      />
      <Table
        style={{ marginTop: 16 }}
        rowKey="id" size="small" pagination={false} dataSource={orders} loading={ordersQ.isLoading}
        columns={[
          { title: '订单', dataIndex: 'id', width: 70, render: (v: number) => `#${v}` },
          { title: '金额', dataIndex: 'amount_cents', width: 90, render: (v: number) => `¥${yuan(v)}` },
          { title: '渠道', dataIndex: 'channel', width: 100, render: (v: string) => CHANNEL_LABEL[v] || v },
          { title: '状态', dataIndex: 'status', width: 90,
            render: (v: string) => <Tag color={v === 'paid' ? 'success' : 'gold'}>{v === 'paid' ? '已到账' : '待确认'}</Tag> },
          { title: '创建时间', dataIndex: 'created_at', render: (v: string) => new Date(v).toLocaleString('zh-CN') },
        ]}
        locale={{ emptyText: '暂无订单' }}
      />
    </Card>
  )
}

export default BillingPanel
