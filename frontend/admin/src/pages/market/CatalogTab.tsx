/**
 * T-11（FR-04/附加 d）+ T-15（FR-02）：治理目录表格。
 * 行操作：精选星标（乐观更新失败回滚）/ 示例维护弹窗 / 名称单元格点开详情抽屉。
 * 工具栏「清理失源资产」（仅超管）→ PruneConfirmModal 二段式确认。
 */
import React, { useCallback, useEffect, useState } from 'react'
import { Alert, Button, Empty, Select, Space, Table, Tag, Typography, message } from 'antd'
import { DeleteOutlined, ReloadOutlined, StarFilled, StarOutlined } from '@ant-design/icons'

import {
  listAssets, patchFeatured, type AssetRow,
} from '../../services/capabilities'
import { usePermission } from '../../hooks/usePermission'
import { apiErrorMessage } from '../../utils/errorMessage'
import AssetDetailDrawer from './AssetDetailDrawer'
import ExamplesModal from './ExamplesModal'
import ListingControls from './ListingControls'
import PruneConfirmModal from './PruneConfirmModal'
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

type Props = {
  focusName?: string | null
  refreshKey?: number
  canSubscribe?: boolean
  onSubscribe?: (type: string, name: string) => void
}

const matchesFocus = (row: AssetRow, focus: string): boolean => (
  row.name === focus
  || row.title === focus
  || row.name.endsWith(`__${focus}`)
)

const CatalogTab: React.FC<Props> = ({
  focusName, refreshKey, canSubscribe = true, onSubscribe = () => undefined,
}) => {
  const { isPlatformAdmin } = usePermission()
  const [rows, setRows] = useState<AssetRow[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [type, setType] = useState<string | undefined>()
  const [listing, setListing] = useState<string | undefined>()
  const [notice, setNotice] = useState<string | null>(null)
  const [starPending, setStarPending] = useState<number | null>(null)
  const [examplesRow, setExamplesRow] = useState<AssetRow | null>(null)
  const [pruneOpen, setPruneOpen] = useState(false)
  const [detailRow, setDetailRow] = useState<AssetRow | null>(null)

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

  const toggleFeatured = async (row: AssetRow) => {
    if (starPending) return
    const next = !row.featured
    setStarPending(row.id)
    // 乐观更新：行数据先翻转，失败回滚（edge-states §7.1）
    replace({ ...row, featured: next })
    try {
      replace(await patchFeatured(row.asset_type, row.name, next))
    } catch (e) {
      replace({ ...row, featured: !next })
      message.error(`操作失败：${apiErrorMessage(e, '请稍后重试')}`)
    } finally {
      setStarPending(null)
    }
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
        {isPlatformAdmin ? (
          <Button danger icon={<DeleteOutlined />} aria-label="清理失源资产"
                  onClick={() => setPruneOpen(true)}>
            清理失源资产
          </Button>
        ) : null}
      </Space>
      {empty ? (
        <Empty description={filtered ? '没有符合条件的目录项' : CATALOG_EMPTY} />
      ) : (
        <Table rowKey="id" size="middle" loading={loading} dataSource={rows}
               pagination={GOVERNANCE_PAGINATION}
               rowClassName={(r) => (focus && matchesFocus(r, focus) ? 'market-catalog-focus' : '')}
               columns={[
                 {
                   title: '名称',
                   dataIndex: 'name',
                   render: (v: string, r: AssetRow) => (
                     <Button
                       type="link"
                       className="market-catalog-name"
                       aria-label={`查看 ${r.title || v} 详情`}
                       onClick={() => setDetailRow(r)}
                     >
                       <Text code>{v}</Text>
                     </Button>
                   ),
                 },
                 { title: '类型', dataIndex: 'asset_type' },
                 { title: '治理', dataIndex: 'status' },
                 {
                   title: '精选',
                   render: (_: unknown, r: AssetRow) => (
                     isPlatformAdmin ? (
                       <Button
                         type="text"
                         aria-label={r.featured ? `取消精选 ${r.name}` : `设为精选 ${r.name}`}
                         icon={r.featured ? <StarFilled /> : <StarOutlined />}
                         loading={starPending === r.id}
                         onClick={() => { void toggleFeatured(r) }}
                       />
                     ) : (
                       <Tag>{r.featured ? '精选' : '—'}</Tag>
                     )
                   ),
                 },
                 { title: '上架', render: (_: unknown, r: AssetRow) => (
                   <ListingControls row={r} isPlatformAdmin={isPlatformAdmin}
                                    onChanged={replace} onError={setNotice} />
                 )},
                 { title: '操作', render: (_: unknown, r: AssetRow) => (
                   <Space>
                     {isPlatformAdmin ? (
                       <Button size="small" onClick={() => setExamplesRow(r)}>示例</Button>
                     ) : null}
                   </Space>
                 )},
               ]} />
      )}
      <ExamplesModal
        open={Boolean(examplesRow)}
        asset={examplesRow}
        onClose={() => setExamplesRow(null)}
        onSaved={replace}
      />
      <PruneConfirmModal
        open={pruneOpen}
        onClose={() => setPruneOpen(false)}
        onPruned={() => { void load() }}
      />
      <AssetDetailDrawer
        open={Boolean(detailRow)}
        assetType={detailRow?.asset_type || ''}
        name={detailRow?.name || ''}
        canSubscribe={canSubscribe}
        onSubscribe={onSubscribe}
        onClose={() => setDetailRow(null)}
      />
    </div>
  )
}

export default CatalogTab
