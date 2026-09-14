/**
 * T-09 结账：W2 主钮「提交开通」；未配通道仍可待支付；闭集待支付/已开通。
 * 禁 live 收银台；租户闭集待支付/已开通；重复提交只「已有待支付」。
 */
import React, { useState } from 'react'
import { Alert, Button, Skeleton, Typography, message } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'

import { LoadFailure } from '../components/LoadState'
import {
  CHECKOUT_FULFILLED_COPY,
  CHECKOUT_OFFLINE_OPEN,
  CHECKOUT_OFFLINE_PAY,
  CHECKOUT_OPEN_FAILED,
  CHECKOUT_PENDING_COPY,
  CHECKOUT_PENDING_EXISTS,
  CHECKOUT_PENDING_EXISTS_COPY,
  CHECKOUT_PRODUCTS,
  CHECKOUT_RETURN_PRICING,
  CHECKOUT_SUBMIT,
  CHECKOUT_SUBMIT_LOADING,
  CHECKOUT_SUPERADMIN_FORBIDDEN,
  CHECKOUT_UNCONFIGURED_PENDING,
  CHECKOUT_UNKNOWN_PRODUCT,
  CONTACT_ADMIN_COPY,
  CONTACT_ADMIN_DETAIL,
  DEFAULT_UPGRADE_PRODUCT,
  ORDER_PENDING_EXISTS,
  ORDER_ROLE_NOT_ALLOWED,
  PRICING_PATH,
} from '../constants/collectCopy'
import {
  createCheckout,
  listMyOrders,
  previewCheckout,
  type CheckoutPreview,
  type OrderRow,
} from '../services/billing'
import { apiErrorCode } from '../utils/collectBlock'
import { apiErrorMessage } from '../utils/errorMessage'
import { isFulfilledStatus, tenantOrderStatus } from '../utils/orderStatus'

const { Text, Title } = Typography

const PRODUCT_LABEL: Record<string, string> = {
  plan_pro: '专业档',
  plan_enterprise: '企业档',
  relay: '中转',
}

const isOffline = () => typeof navigator !== 'undefined' && navigator.onLine === false

const channelsAllUnconfigured = (channels: CheckoutPreview['channels'] | undefined): boolean =>
  Array.isArray(channels) && channels.length > 0 && channels.every((c) => c.configured === false)

/** Pending 金标：can_pay=false，或 notice/empty_state 金标句，或通道全未配。 */
const showUnconfiguredPendingCopy = (data: CheckoutPreview | undefined, pending: boolean): boolean => {
  if (!pending || !data) return false
  if (data.can_pay === false) return true
  if (data.notice === CHECKOUT_UNCONFIGURED_PENDING || data.empty_state === CHECKOUT_UNCONFIGURED_PENDING) {
    return true
  }
  return channelsAllUnconfigured(data.channels)
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
  const [dupHint, setDupHint] = useState(false)

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

  const submitMutation = useMutation({
    mutationFn: () => createCheckout({ product }),
    onSuccess: () => {
      setDupHint(false)
      invalidate()
    },
    onError: (e) => {
      const code = apiErrorCode(e)
      if (code === CHECKOUT_PENDING_EXISTS || code === ORDER_PENDING_EXISTS) {
        setDupHint(true)
        invalidate()
        return
      }
      if (code === ORDER_ROLE_NOT_ALLOWED) {
        message.warning(CONTACT_ADMIN_COPY)
        return
      }
      message.error(apiErrorMessage(e, CHECKOUT_OPEN_FAILED))
    },
  })

  const openOrder = findOpenOrder(ordersQuery.data, orderId)
  const openStatus = openOrder?.status || ''
  const fulfilled = isFulfilledStatus(openStatus)
  const pending = Boolean(orderId && !fulfilled) || dupHint

  const onSubmit = () => {
    if (isOffline()) {
      message.warning(CHECKOUT_OFFLINE_PAY)
      return
    }
    submitMutation.mutate()
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
        <Alert type="info" showIcon title={apiErrorMessage(previewQuery.error, '超管不能代企业支付')} />
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
  const amount = typeof data?.amount_cents === 'number' ? data.amount_cents : null
  const unconfigured = showUnconfiguredPendingCopy(data, pending)

  return (
    <div data-testid="checkout-page">
      <Title level={4} style={{ marginTop: 0 }}>
        {PRODUCT_LABEL[product] || product}
      </Title>
      {amount != null && (
        <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
          ¥{(amount / 100).toLocaleString('en-US')}
        </Text>
      )}

      {dupHint && (
        <Alert type="warning" showIcon style={{ marginBottom: 16 }} title={CHECKOUT_PENDING_EXISTS_COPY} />
      )}

      {fulfilled && (
        <Alert type="success" showIcon title={CHECKOUT_FULFILLED_COPY} />
      )}

      {!fulfilled && pending && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          title={tenantOrderStatus(openStatus)}
          description={unconfigured ? CHECKOUT_UNCONFIGURED_PENDING : undefined}
        />
      )}

      {!fulfilled && !pending && (
        <Button
          type="primary"
          disabled={submitMutation.isPending}
          loading={submitMutation.isPending}
          onClick={onSubmit}
        >
          {submitMutation.isPending ? CHECKOUT_SUBMIT_LOADING : CHECKOUT_SUBMIT}
        </Button>
      )}
    </div>
  )
}

export default Checkout
