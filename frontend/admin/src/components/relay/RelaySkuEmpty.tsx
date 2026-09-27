/**
 * T-20 / T-16 屏 13：SKU none / expired 空态。未开通只「未开通中转」。
 */
import React from 'react'
import { Alert, Button } from 'antd'

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
  onUpgrade: () => void
}

const RelaySkuEmpty: React.FC<RelaySkuEmptyProps> = ({
  status, title, hint, onUpgrade,
}) => {
  const expired = status === 'expired'
  const heading = title || (expired ? RELAY_SKU_EXPIRED : RELAY_SKU_NONE)
  const detail = hint || (expired ? RELAY_SKU_EXPIRED_HINT : RELAY_SKU_NONE_HINT)
  return (
    <div data-testid="relay-sku-empty">
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
