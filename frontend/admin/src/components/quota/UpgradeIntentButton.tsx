import React, { useState } from 'react'
import { Button, message } from 'antd'
import { useNavigate } from 'react-router-dom'

import {
  CHECKOUT_OPENING,
  DEFAULT_UPGRADE_PRODUCT,
  PRICING_CTA_CHECKOUT,
  UPGRADE_CTA,
  UPGRADE_OFFLINE_COPY,
} from '../../constants/collectCopy'
import { fetchUpgradeIntent } from '../../services/usage'
import { apiErrorMessage } from '../../utils/errorMessage'
import { ContactAdminModal } from './ContactAdminModal'

interface UpgradeIntentButtonProps {
  product?: string
  size?: 'small' | 'middle'
  label?: string
}

/** 「申请提升」/「去结账」：upgrade-intent 分角色。不建单。 */
export const UpgradeIntentButton: React.FC<UpgradeIntentButtonProps> = ({
  product = DEFAULT_UPGRADE_PRODUCT,
  size = 'small',
  label = UPGRADE_CTA,
}) => {
  const navigate = useNavigate()
  const [contactOpen, setContactOpen] = useState(false)
  const [loading, setLoading] = useState(false)

  const onClick = async () => {
    if (typeof navigator !== 'undefined' && navigator.onLine === false) {
      message.warning(UPGRADE_OFFLINE_COPY)
      return
    }
    setLoading(true)
    try {
      const intent = await fetchUpgradeIntent(product)
      if (intent.action === 'checkout' && intent.checkout_path) {
        navigate(intent.checkout_path)
        return
      }
      setContactOpen(true)
    } catch (e) {
      message.error(apiErrorMessage(e, UPGRADE_OFFLINE_COPY))
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <Button type="primary" size={size} loading={loading} onClick={onClick}>
        {loading && label === PRICING_CTA_CHECKOUT ? CHECKOUT_OPENING : label}
      </Button>
      <ContactAdminModal open={contactOpen} onClose={() => setContactOpen(false)} />
    </>
  )
}
