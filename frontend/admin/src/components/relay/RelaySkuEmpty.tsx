/**
 * T-20 屏 13：SKU none / expired 空态。去升级 CTA 由父组件分角色落地。
 */
import React from 'react'
import { Alert, Button } from 'antd'

import { CHECKOUT_PAID_PENDING_COPY, CHECKOUT_REFRESH } from '../../constants/collectCopy'
import {
  RELAY_SKU_EXPIRED,
  RELAY_SKU_EXPIRED_HINT,
  RELAY_SKU_NONE,
  RELAY_SKU_NONE_HINT,
  RELAY_UPGRADE_CTA,
} from '../../constants/relayCopy'

interface RelaySkuEmptyProps {
  status: string
  title?: string
  hint?: string
  fulfillmentPending?: boolean
  onUpgrade: () => void
  onRefresh?: () => void
}

const RelaySkuEmpty: React.FC<RelaySkuEmptyProps> = ({
  status, title, hint, fulfillmentPending, onUpgrade, onRefresh,
}) => {
  const expired = status === 'expired'
  const heading = title || (expired ? RELAY_SKU_EXPIRED : RELAY_SKU_NONE)
  const detail = hint || (expired ? RELAY_SKU_EXPIRED_HINT : RELAY_SKU_NONE_HINT)
  return (
    <div data-testid="relay-sku-empty">
      {fulfillmentPending && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          title={CHECKOUT_PAID_PENDING_COPY}
          action={onRefresh
            ? <Button size="small" onClick={onRefresh}>{CHECKOUT_REFRESH}</Button>
            : undefined}
        />
      )}
      <Alert
        type="info"
        showIcon
        title={heading}
        description={detail}
        action={<Button type="primary" size="small" onClick={onUpgrade}>{RELAY_UPGRADE_CTA}</Button>}
      />
    </div>
  )
}

export default RelaySkuEmpty
