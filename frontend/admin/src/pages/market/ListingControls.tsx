import React, { useState } from 'react'
import { Modal, Radio, Space, Typography } from 'antd'

import { patchListing, type AssetRow } from '../../services/capabilities'
import { apiErrorMessage } from '../../utils/errorMessage'
import {
  LISTING_OPTIONS, NEED_PLATFORM_MARKET, thirdPartyConfirm,
} from './marketCopy'

const { Text } = Typography

const isThirdParty = (row: AssetRow): boolean =>
  Boolean(row.source_type && row.source_type !== 'self_built')

type Props = {
  row: AssetRow
  isPlatformAdmin: boolean
  onChanged: (next: AssetRow) => void
  onError: (msg: string) => void
}

const ListingControls: React.FC<Props> = ({
  row, isPlatformAdmin, onChanged, onError,
}) => {
  const [pending, setPending] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const apply = async (listing_state: string, confirm = false) => {
    setBusy(true)
    try {
      const next = await patchListing(row.asset_type, row.name, listing_state, confirm)
      onChanged({ ...row, ...next })
    } catch (e) {
      onError(apiErrorMessage(e, '上架失败'))
    } finally {
      setBusy(false)
      setPending(null)
    }
  }

  const onSelect = (value: string) => {
    if (value === row.listing_state) return
    if (value === 'listed' && isThirdParty(row)) {
      setPending(value)
      return
    }
    apply(value)
  }

  return (
    <Space orientation="vertical" size={0}>
      <div role="group" aria-label={`上架 ${row.name}`}>
      <Radio.Group
        size="small"
        optionType="button"
        value={row.listing_state || 'unlisted'}
        options={[...LISTING_OPTIONS]}
        disabled={!isPlatformAdmin || busy}
        onChange={(e) => onSelect(e.target.value)}
      />
      </div>
      {!isPlatformAdmin ? <Text type="secondary">{NEED_PLATFORM_MARKET}</Text> : null}
      {row.listed_at ? <Text type="secondary">最近上架 {row.listed_at}</Text> : null}
      <Modal
        open={Boolean(pending)}
        title={thirdPartyConfirm(row.name)}
        okText="确认上架"
        cancelText="取消"
        onOk={() => pending && apply(pending, true)}
        onCancel={() => setPending(null)}
        confirmLoading={busy}
      />
    </Space>
  )
}

export default ListingControls
