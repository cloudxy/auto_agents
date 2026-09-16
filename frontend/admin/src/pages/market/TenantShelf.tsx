/**
 * T-08（FR-03/04）：市场货架壳——Tabs + 排序组（综合/最热/最新，URL ?sort=）+
 * 筛选条 + 状态路由（骨架/三重空态/错/网格/分页）+ 详情抽屉。
 * 刷新（切 tab/换排序/翻页）保留旧卡（透明 0.6 + 顶部细进度条），不变骨架。
 * 超管预览态：badge + tab 空态 [立即同步] 治理行动（edge-states §4.4）。
 */
import React, { useEffect, useMemo, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Alert, Button, Input, Segmented, Select, Skeleton, Tabs, message } from 'antd'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { listPublicAssets, syncAgentsHub, type PublicShelfItem } from '../../services/capabilities'
import { usePermission } from '../../hooks/usePermission'
import { apiErrorMessage } from '../../utils/errorMessage'
import { syncDoneCopy, syncFailCopy } from './marketCopy'
import AssetDetailDrawer from './AssetDetailDrawer'
import ShelfCard from './ShelfCard'
import {
  EMPTY_SHELF, FILTER_EMPTY, GO_GOVERNANCE, HOST_OPTIONS, LOAD_FAIL,
  LOAD_FAIL_HINT, MARKET_CLOSED, PREVIEW_BADGE, PUBLIC_TYPES, SORT_OPTIONS,
  SYNC_NOW, TAB_EMPTY, emptyShelfHint, hasActiveFilters, resolveSort, resolveType,
  tabEmptyHint, typeLabelOf,
} from './shelfCopy'
import './TenantShelf.css'

type FilterPatch = Record<string, string>

type Props = {
  canSubscribe: boolean
  onSubscribe: (type: string, name: string) => void
  /** T-13：超管预览态退出预览回治理壳；租户侧缺省跳 /capabilities */
  onExitPreview?: () => void
}

const MarketSkeleton: React.FC = () => (
  <div className="tenant-shelf__grid" data-testid="market-skeleton" aria-busy="true">
    {Array.from({ length: 6 }, (_, i) => (
      <div key={i} className="tenant-shelf__skel"><Skeleton active title paragraph={{ rows: 3 }} /></div>
    ))}
  </div>
)

const FilterEcho: React.FC<{ filters: { q: string; host: string; category: string } }> = ({ filters }) => {
  const rows: Array<{ key: string; label: string; value: string }> = []
  if (filters.q) rows.push({ key: 'q', label: '关键词', value: filters.q })
  if (filters.host) rows.push({ key: 'host', label: '宿主', value: filters.host })
  if (filters.category) rows.push({ key: 'category', label: '分类', value: filters.category })
  return (
    <ul data-testid="filter-echo" className="tenant-shelf__echo">
      {rows.map((row) => (
        <li key={row.key}>{`${row.label}：${row.value}`}</li>
      ))}
    </ul>
  )
}

/** T-08 tab 类型空态（GWT-03.3）：[立即同步] 仅超管预览态渲染（治理动作在治理面） */
const TypeTabEmpty: React.FC<{
  typeKey: string
  canSync: boolean
  syncing: boolean
  onSync: () => void
  onGoGovernance: () => void
}> = ({ typeKey, canSync, syncing, onSync, onGoGovernance }) => (
  <div className="tenant-shelf__empty" data-testid="type-tab-empty">
    <p>{TAB_EMPTY}</p>
    <p className="tenant-shelf__empty-hint">{tabEmptyHint(typeLabelOf(typeKey))}</p>
    <div className="tenant-shelf__empty-actions">
      {canSync ? (
        <Button type="primary" loading={syncing} onClick={onSync}>{SYNC_NOW}</Button>
      ) : null}
      <Button onClick={onGoGovernance}>{GO_GOVERNANCE}</Button>
    </div>
  </div>
)

const MarketEmpty: React.FC<{
  closed: boolean
  filtered: boolean
  liveTotal?: number | null
  onClear: () => void
}> = ({ closed, filtered, liveTotal, onClear }) => {
  if (closed) {
    return (
      <div className="tenant-shelf__empty" data-testid="market-closed">
        <p>{MARKET_CLOSED}</p>
        <p className="tenant-shelf__empty-hint">开放后，已上架的能力会出现在这里。</p>
      </div>
    )
  }  if (filtered) {
    return (
      <div className="tenant-shelf__empty" data-testid="filter-empty">
        <p>{FILTER_EMPTY}</p>
        <Button onClick={onClear} autoInsertSpace={false}>清除筛选</Button>
      </div>
    )
  }
  return (
    <div className="tenant-shelf__empty" data-testid="empty-shelf">
      <p>{EMPTY_SHELF}</p>
      <p className="tenant-shelf__empty-hint">{emptyShelfHint(liveTotal)}</p>
    </div>
  )
}

type GridProps = {
  type: string
  q: string
  host: string
  category: string
  page: number
  sort: string
  onPage: (page: number) => void
  onClear: () => void
  onOpenAsset: (item: PublicShelfItem) => void
}

const AssetGrid: React.FC<GridProps> = ({
  type, q, host, category, page, sort, onPage, onClear, onOpenAsset,
}) => {
  const { isPlatformAdmin } = usePermission()
  const [syncing, setSyncing] = useState(false)
  const typeParam = type === 'all' ? undefined : type
  const query = useQuery({
    queryKey: ['admin', 'public-capabilities', typeParam, q, host, category, page, sort],
    queryFn: () => listPublicAssets({
      type: typeParam, q: q || undefined, host: host || undefined,
      category: category || undefined, page, sort,
    }),
    placeholderData: keepPreviousData,
    retry: false,
  })
  if (query.isLoading) return <MarketSkeleton />
  if (query.isError) {
    return (
      <div className="tenant-shelf__error" role="alert">
        <p>{LOAD_FAIL}</p>
        <p>{LOAD_FAIL_HINT}</p>
        <Button type="primary" onClick={() => { void query.refetch() }} loading={query.isFetching} autoInsertSpace={false}>
          重试
        </Button>
      </div>
    )
  }
  const items = query.data?.items || []
  const total = query.data?.total ?? 0
  const closed = query.data?.market_closed === true
  const filtered = Boolean(q || host || category)
  const tabEmpty = !closed && !filtered && Boolean(typeParam)
  const previewBadge = query.data?.preview === true && query.data?.gate_open === false
  // 刷新（切 tab/排序/翻页）：保旧卡半透明 + 顶部进度条（<200ms 由 CSS 延迟防闪烁）
  const stale = query.isFetching && items.length > 0

  const syncNow = async () => {
    if (syncing) return
    setSyncing(true)
    try {
      const result = await syncAgentsHub()
      message.success(syncDoneCopy(result.inserted, result.updated, result.unchanged))
      await query.refetch()
    } catch (e) {
      message.error(syncFailCopy(apiErrorMessage(e, '请稍后重试')))
    } finally {
      setSyncing(false)
    }
  }

  return (
    <div aria-busy={stale || undefined}>
      {previewBadge ? (
        <Alert type="info" showIcon title={PREVIEW_BADGE} data-testid="shelf-preview-badge" style={{ marginBottom: 12 }} />
      ) : null}
      {closed || (!items.length && total === 0) ? (
        tabEmpty ? (
          <TypeTabEmpty
            typeKey={typeParam as string}
            canSync={isPlatformAdmin && query.data?.preview === true}
            syncing={syncing}
            onSync={syncNow}
            onGoGovernance={onClear}
          />
        ) : (
          <MarketEmpty
            closed={closed}
            filtered={filtered}
            liveTotal={query.data?.live_total}
            onClear={onClear}
          />
        )
      ) : !items.length ? (
        <div className="tenant-shelf__empty"><p>没有更多了</p></div>
      ) : (
        <>
          {stale ? <div className="tenant-shelf__progress" role="presentation" /> : null}
          <div className={`tenant-shelf__grid${stale ? ' tenant-shelf__grid--stale' : ''}`}>
            {items.map((item) => (
              <ShelfCard key={`${item.asset_type}-${item.name}`} item={item} onOpen={onOpenAsset} />
            ))}
          </div>
          {total > 0 ? (
            <nav className="tenant-shelf__pager" data-testid="market-pager" aria-label="翻页">
              <span>共 {total} 件</span>
              {page > 1 ? <Button onClick={() => onPage(page - 1)} autoInsertSpace={false}>上一页</Button> : null}
              {query.data?.has_more ? (
                <Button type="primary" onClick={() => onPage(page + 1)} autoInsertSpace={false}>下一页</Button>
              ) : null}
            </nav>
          ) : null}
        </>
      )}
    </div>
  )
}

function writeParams(prev: URLSearchParams, patch: FilterPatch): URLSearchParams {
  const next = new URLSearchParams(prev)
  Object.entries(patch).forEach(([key, value]) => {
    const trimmed = value.trim()
    if (!trimmed) next.delete(key)
    else next.set(key, trimmed)
  })
  return next
}

const TenantShelf: React.FC<Props> = ({ canSubscribe, onSubscribe, onExitPreview }) => {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const rawType = searchParams.get('type')
  const resolved = useMemo(() => resolveType(rawType), [rawType])
  const q = searchParams.get('q') || ''
  const host = searchParams.get('host') || ''
  const category = searchParams.get('category') || ''
  const sort = resolveSort(searchParams.get('sort'))
  const page = Math.max(1, Number.parseInt(searchParams.get('page') || '1', 10) || 1)
  const [draftQ, setDraftQ] = useState(q)
  const [draftCat, setDraftCat] = useState(category)
  const [selected, setSelected] = useState<PublicShelfItem | null>(null)
  useEffect(() => { setDraftQ(q) }, [q])
  useEffect(() => { setDraftCat(category) }, [category])

  const patchParams = (partial: FilterPatch) => {
    setSearchParams((prev) => {
      const next = writeParams(prev, partial)
      if (!('page' in partial)) next.delete('page')
      return next
    }, { replace: true })
  }
  const onPage = (target: number) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (target <= 1) next.delete('page')
      else next.set('page', String(target))
      return next
    })
  }
  const goGovernance = () => (onExitPreview ? onExitPreview() : navigate('/capabilities'))

  return (
    <div className="tenant-shelf" data-testid="tenant-shelf">
      <h1 className="tenant-shelf__heading">能力市场</h1>
      {resolved.illegal ? (
        <div className="tenant-shelf__empty">
          <p>没有这种类型</p>
          <Button type="primary" onClick={() => patchParams({ type: '' })} autoInsertSpace={false}>查看全部</Button>
        </div>
      ) : (
        <>
          <Tabs
            activeKey={resolved.key}
            onChange={(key) => patchParams({ type: key === 'all' ? '' : key })}
            tabBarExtraContent={{
              right: (
                <Segmented
                  aria-label="排序"
                  value={sort}
                  options={[...SORT_OPTIONS]}
                  onChange={(value) => patchParams({ sort: value === 'smart' ? '' : String(value) })}
                />
              ),
            }}
            items={[
              { key: 'all', label: '全部' },
              ...PUBLIC_TYPES.map((t) => ({ key: t.key, label: t.label })),
            ]}
          />
          <div className="tenant-shelf__filters">
            <Input.Search
              allowClear
              enterButton={<Button type="primary" autoInsertSpace={false}>搜索</Button>}
              placeholder="展示名或短名"
              value={draftQ}
              onChange={(e) => setDraftQ(e.target.value)}
              onSearch={(value) => patchParams({ q: value })}
              aria-label="搜索能力"
            />
            <Select
              allowClear
              aria-label="宿主"
              placeholder="宿主"
              value={host || undefined}
              options={[...HOST_OPTIONS]}
              onChange={(value) => patchParams({ host: value || '' })}
            />
            <Input
              allowClear
              aria-label="分类"
              placeholder="分类"
              value={draftCat}
              onChange={(e) => setDraftCat(e.target.value)}
              onPressEnter={(e) => patchParams({ category: e.currentTarget.value })}
              onBlur={(e) => patchParams({ category: e.currentTarget.value })}
            />
          </div>
          <AssetGrid
            type={resolved.key}
            q={q}
            host={host}
            category={category}
            page={page}
            sort={sort}
            onPage={onPage}
            onClear={goGovernance}
            onOpenAsset={setSelected}
          />
          <AssetDetailDrawer
            open={Boolean(selected)}
            assetType={selected?.asset_type || ''}
            name={selected?.name || ''}
            canSubscribe={canSubscribe}
            onSubscribe={onSubscribe}
            onClose={() => setSelected(null)}
          />
        </>
      )}
    </div>
  )
}

export default TenantShelf
