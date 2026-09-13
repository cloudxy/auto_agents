import React, { useState } from 'react'
import { Button, message } from 'antd'
import { useNavigate } from 'react-router-dom'

import {
  DEFAULT_UPGRADE_PRODUCT,
  UPGRADE_CTA,
  UPGRADE_OFFLINE_COPY,
} from '../../constants/collectCopy'
import { fetchUpgradeIntent } from '../../services/usage'
import { apiErrorMessage } from '../../utils/errorMessage'
import { ContactAdminModal } from './ContactAdminModal'

interface UpgradeIntentButtonProps {
  product?: string
  size?: 'small' | 'middle'
}

/** 「申请提升」：upgrade-intent 分角色（经办/只读→屏 10；买方→结账空态）。不建单。 */
export const UpgradeIntentButton: React.FC<UpgradeIntentButtonProps> = ({
  product = DEFAULT_UPGRADE_PRODUCT,
  size = 'small',
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
        {UPGRADE_CTA}
      </Button>
      <ContactAdminModal open={contactOpen} onClose={() => setContactOpen(false)} />
    </>
  )
}
