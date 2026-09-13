/**
 * 企业空间专属页说明（T-15 / GWT-82.4）：平台超管无企业空间（tenant_id=NULL）
 * 打开租户产品页时，给「用量/安装属于企业空间」同类说明态——
 * 不是空表假装没订阅。平台租户身份（FR-102）仅用于采集入队与方案归属，
 * 不改变本说明。与 Usage 页「用量属于企业空间」同形。
 */
import React from 'react'
import { Alert } from 'antd'

const TenantSpaceOnly: React.FC<{ what: string }> = ({ what }) => (
  <Alert type="info" showIcon title={`${what}属于企业空间`} />
)

export default TenantSpaceOnly
