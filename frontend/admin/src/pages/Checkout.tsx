/**
 * T-19 结账：支付宝 / 微信支付选择；未配空态 / 待支付 / 开通处理中。
 * 买方 POST /billing/checkout；经办/只读 → 屏 10。不接 notify。禁 FR-U24 四字。
 */
import React, { useMemo, useState } from 'react'
import { Alert, Button, Radio, Skeleton, Space, Typography, message } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'

import { LoadFailure } from '../components/LoadState'
import {
  BILLING_CHANNELS_UNCONFIGURED,
  BILLING_CHANNEL_UNCONFIGURED,
  CHANNEL_ALIPAY,
  CHANNEL_UNCONFIGURED_COPY,
  CHANNEL_WECHAT,
  CHECKOUT_CONTINUE_PAY,
  CHECKOUT_EMPTY_COPY,
  CHECKOUT_EMPTY_DETAIL,
  CHECKOUT_GO_PAY,
  CHECKOUT_GO_PAY_LOADING,
  CHECKOUT_OFFLINE_CONTINUE,
  CHECKOUT_OFFLINE_OPEN,
  CHECKOUT_OFFLINE_PAY,
  CHECKOUT_OPEN_FAILED,
  CHECKOUT_PAID_PENDING_COPY,
  CHECKOUT_PENDING_COPY,
  CHECKOUT_PENDING_EXISTS,
  CHECKOUT_PENDING_EXISTS_COPY,
  CHECKOUT_PRODUCTS,
  CHECKOUT_REFRESH,
  CHECKOUT_RETRY_CHECKOUT,
  CHECKOUT_RETURN_PRICING,
  CHECKOUT_SUPERADMIN_FORBIDDEN,
  CHECKOUT_UNKNOWN_PRODUCT,
  CHECKOUT_UNPAID_PLAN,
  CHECKOUT_UNPAID_RELAY,
  CONTACT_ADMIN_COPY,
  CONTACT_ADMIN_DETAIL,
  DEFAULT_UPGRADE_PRODUCT,
  ORDER_ROLE_NOT_ALLOWED,
  PRICING_PATH,
} from '../constants/collectCopy'
import {
  createCheckout,
  listMyOrders,
  previewCheckout,
  type CheckoutChannel,
  type OrderRow,
  type PayChannel,
} from '../services/billing'
import { apiErrorCode } from '../utils/collectBlock'
import { apiErrorMessage } from '../utils/errorMessage'

const { Text, Title } = Typography

const PRODUCT_LABEL: Record<string, string> = {
  plan_pro: '专业档',
  plan_enterprise: '企业档',
  relay: '中转',
}

const CHANNEL_LABEL: Record<PayChannel, string> = {
  alipay: CHANNEL_ALIPAY,
  wechat: CHANNEL_WECHAT,
}

const PENDING_STATUSES = new Set(['checkout_pending', 'pending'])
const PAID_PENDING = 'paid_pending_fulfillment'
const UNPAID_STATUSES = new Set(['unpaid', 'cancelled'])

const isOffline = () => typeof navigator !== 'undefined' && navigator.onLine === false

const channelLabel = (ch: string | undefined): string => {
  if (ch === 'alipay' || ch === 'wechat') return CHANNEL_LABEL[ch]
  return ''
}

const findOpenOrder = (orders: OrderRow[] | undefined, orderId: number | null): OrderRow | undefined => {
  if (!orders || orderId == null) return undefined
  return orders.find((row) => row.id === orderId)
}

const Checkout: React.FC = () => {
  const queryClient = useQueryClient()
  const [params] = useSearchParams()
  const product = params.get('product') || DEFAULT_UPGRADE_PRODUCT
  const knownProduct = (CHECKOUT_PRODUCTS as readonly string[]).includes(product)
  const [picked, setPicked] = useState<PayChannel | null>(null)
  const [inlineHint, setInlineHint] = useState<string | null>(null)

  const previewQuery = useQuery({
    queryKey: ['billing-checkout', product],
    queryFn: () => previewCheckout(product),
    enabled: knownProduct,
    retry: false,
  })
  const orderId = previewQuery.data?.order_id ?? null
  const ordersQuery = useQuery({
    queryKey: ['my-orders'],
    queryFn: listMyOrders,
    enabled: knownProduct && orderId != null,
    retry: false,
  })

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['billing-checkout', product] })
    void queryClient.invalidateQueries({ queryKey: ['my-orders'] })
  }

  const payMutation = useMutation({
    mutationFn: (channel: PayChannel) => createCheckout({ product, channel }),
    onSuccess: () => {
      setInlineHint(null)
      invalidate()
    },
    onError: (e) => {
      const code = apiErrorCode(e)
      if (code === CHECKOUT_PENDING_EXISTS || code === 'ORDER_PENDING_EXISTS') {
        setInlineHint(CHECKOUT_PENDING_EXISTS_COPY)
        invalidate()
        return
      }
      if (code === BILLING_CHANNEL_UNCONFIGURED || code === 'ORDER_CHANNEL_UNCONFIGURED') {
        setInlineHint(CHANNEL_UNCONFIGURED_COPY)
        invalidate()
        return
      }
      if (code === BILLING_CHANNELS_UNCONFIGURED) {
        setInlineHint(CHECKOUT_EMPTY_COPY)
        return
      }
      if (code === ORDER_ROLE_NOT_ALLOWED) {
        setInlineHint(CONTACT_ADMIN_COPY)
        return
      }
      setInlineHint(apiErrorMessage(e, CHECKOUT_OPEN_FAILED))
    },
  })

  const channels: CheckoutChannel[] = previewQuery.data?.channels ?? []
  const selectable = useMemo(
    () => channels.filter((row) => row.selectable).map((row) => row.channel),
    [channels],
  )
  const selected: PayChannel | null = picked && selectable.includes(picked)
    ? picked
    : (selectable[0] ?? null)
  const openOrder = findOpenOrder(ordersQuery.data, orderId)
  const openStatus = openOrder?.status || ''
  const isPaidPending = openStatus === PAID_PENDING
  const isPending = PENDING_STATUSES.has(openStatus) || Boolean(orderId && !openOrder && inlineHint === CHECKOUT_PENDING_EXISTS_COPY)
  const isUnpaid = UNPAID_STATUSES.has(openStatus)

  const onPay = () => {
    if (isOffline()) {
      message.warning(CHECKOUT_OFFLINE_PAY)
      return
    }
    if (!selected) return
    payMutation.mutate(selected)
  }

  const onContinue = () => {
    if (isOffline()) {
      message.warning(CHECKOUT_OFFLINE_CONTINUE)
    }
  }

  if (!knownProduct) {
    return (
      <Alert
        type="warning"
        showIcon
        title={CHECKOUT_UNKNOWN_PRODUCT}
        action={<Button size="small" href={PRICING_PATH}>{CHECKOUT_RETURN_PRICING}</Button>}
      />
    )
  }

  if (previewQuery.isPending || (orderId != null && ordersQuery.isPending && !ordersQuery.data)) {
    return <Skeleton active paragraph={{ rows: 6 }} />
  }

  if (previewQuery.isError) {
    const code = apiErrorCode(previewQuery.error)
    if (code === ORDER_ROLE_NOT_ALLOWED) {
      return (
        <Alert type="info" showIcon title={CONTACT_ADMIN_COPY} description={CONTACT_ADMIN_DETAIL} />
      )
    }
    if (code === 'CHECKOUT_UNKNOWN_PRODUCT') {
      return (
        <Alert
          type="warning"
          showIcon
          title={CHECKOUT_UNKNOWN_PRODUCT}
          action={<Button size="small" href={PRICING_PATH}>{CHECKOUT_RETURN_PRICING}</Button>}
        />
      )
    }
    if (code === CHECKOUT_SUPERADMIN_FORBIDDEN) {
      return (
        <Alert
          type="info"
          showIcon
          title={apiErrorMessage(previewQuery.error, '超管不能代企业支付')}
        />
      )
    }
    if (isOffline()) {
      return (
        <Alert
          type="warning"
          showIcon
          title={CHECKOUT_OFFLINE_OPEN}
          action={<Button size="small" onClick={() => previewQuery.refetch()}>重试</Button>}
        />
      )
    }
    return <LoadFailure title={CHECKOUT_OPEN_FAILED} onRetry={() => previewQuery.refetch()} />
  }

  const data = previewQuery.data
  const bothUnconfigured = !data?.can_pay && orderId == null && !isPaidPending && !isPending
  const unpaidCopy = product === 'relay' ? CHECKOUT_UNPAID_RELAY : CHECKOUT_UNPAID_PLAN

  return (
    <div data-testid="checkout-page">
      <Title level={4} style={{ marginTop: 0 }}>
        {PRODUCT_LABEL[product] || product}
      </Title>
      {typeof data?.amount_cents === 'number' && (
        <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
          ¥{(data.amount_cents / 100).toLocaleString('en-US')}
        </Text>
      )}

      {isPaidPending && (
        <Alert
          type="warning"
          showIcon
          title={CHECKOUT_PAID_PENDING_COPY}
          action={<Button size="small" onClick={() => invalidate()}>{CHECKOUT_REFRESH}</Button>}
        />
      )}

      {!isPaidPending && (isPending || inlineHint === CHECKOUT_PENDING_EXISTS_COPY) && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          title={inlineHint === CHECKOUT_PENDING_EXISTS_COPY ? CHECKOUT_PENDING_EXISTS_COPY : CHECKOUT_PENDING_COPY}
          description={channelLabel(openOrder?.channel || selected || undefined) || undefined}
          action={(
            <Button
              type="primary"
              size="small"
              loading={payMutation.isPending}
              onClick={onContinue}
            >
              {CHECKOUT_CONTINUE_PAY}
            </Button>
          )}
        />
      )}

      {isUnpaid && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          title={unpaidCopy}
          action={<Button size="small" onClick={() => { setInlineHint(null); invalidate() }}>{CHECKOUT_RETRY_CHECKOUT}</Button>}
        />
      )}

      {inlineHint === CHANNEL_UNCONFIGURED_COPY && (
        <Alert type="warning" showIcon style={{ marginBottom: 16 }} title={CHANNEL_UNCONFIGURED_COPY} />
      )}

      {bothUnconfigured && (
        <Alert type="info" showIcon title={data?.empty_state || CHECKOUT_EMPTY_COPY} description={CHECKOUT_EMPTY_DETAIL} />
      )}

      {!isPaidPending && !bothUnconfigured && !isPending && inlineHint !== CHECKOUT_PENDING_EXISTS_COPY && (
        <Space orientation="vertical" size={16} style={{ width: '100%' }}>
          <Radio.Group
            value={selected}
            onChange={(e) => setPicked(e.target.value as PayChannel)}
          >
            <Space orientation="vertical">
              {(['alipay', 'wechat'] as const).map((ch) => {
                const row = channels.find((item) => item.channel === ch)
                const selectableCh = Boolean(row?.selectable)
                return (
                  <Radio key={ch} value={ch} disabled={!selectableCh} data-testid={`channel-${ch}`}>
                    {CHANNEL_LABEL[ch]}
                    {!row?.configured && (
                      <Text type="secondary" style={{ marginLeft: 8 }}>{CHANNEL_UNCONFIGURED_COPY}</Text>
                    )}
                  </Radio>
                )
              })}
            </Space>
          </Radio.Group>
          <Button
            type="primary"
            disabled={!selected || payMutation.isPending}
            loading={payMutation.isPending}
            onClick={onPay}
          >
            {payMutation.isPending ? CHECKOUT_GO_PAY_LOADING : CHECKOUT_GO_PAY}
          </Button>
        </Space>
      )}
    </div>
  )
}

export default Checkout
