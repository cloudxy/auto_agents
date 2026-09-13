import React from 'react'
import { Button, Modal, Typography } from 'antd'

import {
  CONTACT_ADMIN_COPY,
  CONTACT_ADMIN_DETAIL,
  CONTACT_ADMIN_OK,
} from '../../constants/collectCopy'

const { Paragraph } = Typography

interface ContactAdminModalProps {
  open: boolean
  onClose: () => void
}

/** 屏 10：只读/经办申请提升着陆。无注册、无去支付、无 mailto。 */
export const ContactAdminModal: React.FC<ContactAdminModalProps> = ({ open, onClose }) => (
  <Modal
    title={CONTACT_ADMIN_COPY}
    open={open}
    onCancel={onClose}
    footer={[
      <Button key="ok" type="primary" onClick={onClose}>{CONTACT_ADMIN_OK}</Button>,
    ]}
  >
    <Paragraph>{CONTACT_ADMIN_DETAIL}</Paragraph>
  </Modal>
)
