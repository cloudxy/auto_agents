import React, { useCallback, useEffect, useState } from 'react'
import { Alert, Button, Empty, Select, Space, Table, Typography } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'

import { listAssets, type AssetRow } from '../../services/capabilities'
import { usePermission } from '../../hooks/usePermission'
import { apiErrorMessage } from '../../utils/errorMessage'
import ListingControls from './ListingControls'
import {
  CATALOG_EMPTY, GOVERNANCE_PAGINATION, LISTING_OPTIONS, catalogFocusCopy, loadFail,
} from './marketCopy'

const { Text } = Typography

const TYPE_OPTIONS = [
  { value: 'skill', label: '技能' },
  { value: 'plugin', label: '插件' },
  { value: 'command', label: '命令' },
  { value: 'agent', label: '智能体' },
  { value: 'team', label: '专家团' },
]

type Props = { focusName?: string | null; refreshKey?: number }

const matchesFocus = (row: AssetRow, focus: string): boolean => (
  row.name === focus
  || row.title === focus
  || row.name.endsWith(`__${focus}`)
)

const CatalogTab: React.FC<Props> = ({ focusName, refreshKey }) => {
  const { isPlatformAdmin } = usePermission()
  const [rows, setRows] = useState<AssetRow[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [type, setType] = useState<string | undefined>()
  const [listing, setListing] = useState<string | undefined>()
  const [notice, setNotice] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await listAssets(type, listing)
      setRows(data.items)
    } catch (e) {
      setRows([])
      setError(apiErrorMessage(e, loadFail('目录')))
    } finally {
      setLoading(false)
    }
  }, [type, listing])

  // refreshKey（T-36 导入完成计数）为显式重载触发器，不参与 load 逻辑
  useEffect(() => { load() }, [load, refreshKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const replace = (next: AssetRow) => {
    setRows((cur) => cur.map((r) => (r.id === next.id ? { ...r, ...next } : r)))
    setNotice(null)
  }

  const filtered = Boolean(type || listing)
  const empty = !loading && !error && rows.length === 0
  const focus = (focusName || '').trim()

  return (
    <div>
      {focus ? <Alert type="info" showIcon title={catalogFocusCopy(focus)} style={{ marginBottom: 12 }} /> : null}
      {notice ? <Alert type="error" showIcon title={notice} style={{ marginBottom: 12 }} /> : null}
      {error ? (
        <Alert type="error" showIcon title={error} action={<Button onClick={load}>重试</Button>} />
      ) : null}
      <Space style={{ marginBottom: 12 }} wrap>
        <Select allowClear placeholder="类型" style={{ width: 120 }} value={type}
                options={TYPE_OPTIONS} onChange={(v) => setType(v)} />
        <Select allowClear placeholder="上架态" style={{ width: 120 }} value={listing}
                options={[...LISTING_OPTIONS]} onChange={(v) => setListing(v)} />
        <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
      </Space>
      {empty ? (
        <Empty description={filtered ? '没有符合条件的目录项' : CATALOG_EMPTY} />
      ) : (
        <Table rowKey="id" size="middle" loading={loading} dataSource={rows}
               pagination={GOVERNANCE_PAGINATION}
               rowClassName={(r) => (focus && matchesFocus(r, focus) ? 'market-catalog-focus' : '')}
               columns={[
                 { title: '名称', dataIndex: 'name', render: (v: string) => <Text code>{v}</Text> },
                 { title: '类型', dataIndex: 'asset_type' },
                 { title: '治理', dataIndex: 'status' },
                 { title: '上架', render: (_: unknown, r: AssetRow) => (
                   <ListingControls row={r} isPlatformAdmin={isPlatformAdmin}
                                    onChanged={replace} onError={setNotice} />
                 )},
               ]} />
      )}
    </div>
  )
}

export default CatalogTab
