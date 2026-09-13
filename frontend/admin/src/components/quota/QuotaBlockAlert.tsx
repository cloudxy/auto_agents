import React from 'react'
import { Alert, Button } from 'antd'

import { PLAN_FULL_COPY, STORAGE_CTA } from '../../constants/collectCopy'
import { UpgradeIntentButton } from './UpgradeIntentButton'

interface QuotaBlockAlertProps {
  cta: string
  style?: React.CSSProperties
}

/** 配额已尽锁句。存储→去结果库；token/并发→申请提升。禁止工人句。 */
export const QuotaBlockAlert: React.FC<QuotaBlockAlertProps> = ({ cta, style }) => (
  <Alert
    type="error"
    showIcon
    role="alert"
    style={style}
    title={PLAN_FULL_COPY}
    description={
      cta === STORAGE_CTA ? (
        <Button size="small" href="/data">{STORAGE_CTA}</Button>
      ) : (
        <UpgradeIntentButton />
      )
    }
  />
)
