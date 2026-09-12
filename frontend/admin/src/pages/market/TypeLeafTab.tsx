import React, { useCallback, useEffect, useState } from 'react'
import { Alert, Button, Empty, Space, Table, Typography } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'

import { listAssets, type AssetRow } from '../../services/capabilities'
import { usePermission } from '../../hooks/usePermission'
import { apiErrorMessage } from '../../utils/errorMessage'
import ListingControls from './ListingControls'
import { DETAIL, GO_SOURCE, GOVERNANCE_PAGINATION, loadFail } from './marketCopy'

const { Text } = Typography

type Props = {
  types: string[]
  leaf: string
  emptyCopy: string
  onGoSource?: () => void
  onSubscribe?: (name: string) => void
  onDetail?: (row: AssetRow) => void
  extra?: React.ReactNode
}

const TypeLeafTab: React.FC<Props> = ({
  types, leaf, emptyCopy, onGoSource, onSubscribe, onDetail, extra,
}) => {
  const { isPlatformAdmin } = usePermission()
  const [rows, setRows] = useState<AssetRow[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const packs = await Promise.all(types.map((t) => listAssets(t)))
      setRows(packs.flatMap((p) => p.items))
    } catch (e) {
      setRows([])
      setError(apiErrorMessage(e, loadFail(leaf)))
    } finally {
      setLoading(false)
    }
  }, [types, leaf])

  useEffect(() => { load() }, [load])

  const replace = (next: AssetRow) => {
    setRows((cur) => cur.map((r) => (r.id === next.id ? { ...r, ...next } : r)))
    setNotice(null)
  }

  const empty = !loading && !error && rows.length === 0

  return (
    <div>
      {notice ? <Alert type="error" showIcon title={notice} style={{ marginBottom: 12 }} /> : null}
      {error ? (
        <Alert type="error" showIcon title={error} action={<Button onClick={load}>重试</Button>} />
      ) : null}
      <Space style={{ marginBottom: 12 }} wrap>
        {extra}
        <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
      </Space>
      {empty ? (
        <Empty description={emptyCopy}>
          {onGoSource ? <Button onClick={onGoSource}>{GO_SOURCE}</Button> : null}
        </Empty>
      ) : (
        <Table rowKey="id" size="middle" loading={loading} dataSource={rows}
               pagination={GOVERNANCE_PAGINATION}
               columns={[
                 { title: leaf, dataIndex: 'name', render: (v: string, r: AssetRow) => (
                   <Text strong>{r.title || v}</Text>
                 )},
                 { title: '治理', dataIndex: 'status' },
                 { title: '上架', render: (_: unknown, r: AssetRow) => (
                   <ListingControls row={r} isPlatformAdmin={isPlatformAdmin}
                                    onChanged={replace} onError={setNotice} />
                 )},
                 ...(onSubscribe || onDetail ? [{
                   title: '操作',
                   render: (_: unknown, r: AssetRow) => (
                     <Space>
                       {onDetail ? (
                         <Button size="small" onClick={() => onDetail(r)}>{DETAIL}</Button>
                       ) : null}
                       {onSubscribe ? (
                         <Button size="small" onClick={() => onSubscribe(r.name)}>订阅</Button>
                       ) : null}
                     </Space>
                   ),
                 }] : []),
               ]} />
      )}
    </div>
  )
}

export default TypeLeafTab
