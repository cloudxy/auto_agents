import React from 'react'
import { Collapse, Typography } from 'antd'

import { SUB_NE_HOST, SUB_NE_HOST_DETAIL } from './marketCopy'

const { Paragraph } = Typography

const HostRuntimeNote: React.FC = () => (
  <Collapse
    items={[{
      key: 'host',
      label: SUB_NE_HOST,
      children: <Paragraph type="secondary">{SUB_NE_HOST_DETAIL}</Paragraph>,
    }]}
  />
)

export default HostRuntimeNote
