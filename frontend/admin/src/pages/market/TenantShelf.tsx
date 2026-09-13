/**
 * T-10 屏 15：租户货架。订一行发生在这里。无源/上架/扫描/总开关。
 */
import React, { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button, Card, Input, Select, Skeleton, Tabs, Tag, Typography } from 'antd'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { listPublicAssets, type PublicShelfItem } from '../../services/capabilities'
import {
  EMPTY_SHELF, EMPTY_SHELF_HINT, FILTER_EMPTY, HOST_OPTIONS, LOAD_FAIL,
  LOAD_FAIL_HINT, MARKET_CLOSED, MARKET_CLOSED_HINT, PUBLIC_TYPES,
  READONLY_SUBSCRIBE, activeFilterEcho, cardTitle, hasActiveFilters,
  resolveType, type ShelfFilterValues,
} from './shelfCopy'
import './TenantShelf.css'

const { Paragraph } = Typography

type FilterPatch = Record<string, string>

type Props = {
  canSubscribe: boolean
  onSubscribe: (type: string, name: string) => void
}

const MarketSkeleton: React.FC = () => (
  <div className="tenant-shelf__grid" data-testid="market-skeleton" aria-busy="true">
    {Array.from({ length: 6 }, (_, i) => (
      <div key={i} className="tenant-shelf__skel"><Skeleton active title paragraph={{ rows: 3 }} /></div>
    ))}
  </div>
)

const FilterEcho: React.FC<{ filters: ShelfFilterValues }> = ({ filters }) => (
  <ul data-testid="filter-echo" className="tenant-shelf__echo">
    {activeFilterEcho(filters).map((row) => (
      <li key={row.key}>{`${row.label}：${row.value}`}</li>
    ))}
  </ul>
)

const MarketEmpty: React.FC<{
  closed: boolean
  filters: ShelfFilterValues
  onClear: () => void
}> = ({ closed, filters, onClear }) => {
  const filtered = hasActiveFilters(filters)
  if (closed) {
    return (
      <div className="tenant-shelf__empty" data-testid="market-closed">
        <p>{MARKET_CLOSED}</p>
        <p>{MARKET_CLOSED_HINT}</p>
      </div>
    )
  }
  return (
    <div className="tenant-shelf__empty" data-testid={filtered ? 'filter-empty' : 'empty-shelf'}>
      {filtered ? (
        <>
          <p>{FILTER_EMPTY}</p>
          <FilterEcho filters={filters} />
          <Button onClick={onClear} autoInsertSpace={false}>清除筛选</Button>
        </>
      ) : (
        <>
          <p>{EMPTY_SHELF}</p>
          <p>{EMPTY_SHELF_HINT}</p>
        </>
      )}
    </div>
  )
}

const ShelfCard: React.FC<{
  item: PublicShelfItem
  canSubscribe: boolean
  onSubscribe: (type: string, name: string) => void
}> = ({ item, canSubscribe, onSubscribe }) => {
  const title = cardTitle(item)
  const soon = item.listing_state === 'coming_soon'
  const listed = item.listing_state === 'listed' && item.subscribable !== false
  return (
    <Card className="tenant-shelf__card" hoverable>
      <div className="tenant-shelf__card-head">
        <span className="tenant-shelf__title">{title}</span>
        {soon ? <Tag color="processing">预告</Tag> : null}
      </div>
      <Paragraph type="secondary" ellipsis={{ rows: 2 }}>{item.description || '（暂无描述）'}</Paragraph>
      {listed ? (
        <Button
          type="primary"
          autoInsertSpace={false}
          disabled={!canSubscribe}
          title={!canSubscribe ? READONLY_SUBSCRIBE : undefined}
          onClick={() => { if (canSubscribe) onSubscribe(item.asset_type, item.name) }}
        >
          订阅
        </Button>
      ) : null}
    </Card>
  )
}

const AssetGrid: React.FC<{
  type: string
  q: string
  host: string
  category: string
  page: number
  onPage: (page: number) => void
  onClear: () => void
  canSubscribe: boolean
  onSubscribe: (type: string, name: string) => void
}> = ({ type, q, host, category, page, onPage, onClear, canSubscribe, onSubscribe }) => {
  const typeParam = type === 'all' ? undefined : type
  const filters: ShelfFilterValues = { type, q, host, category }
  const query = useQuery({
    queryKey: ['admin', 'public-capabilities', typeParam, q, host, category, page],
    queryFn: () => listPublicAssets({
      type: typeParam, q: q || undefined, host: host || undefined,
      category: category || undefined, page,
    }),
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
  if (closed || (!items.length && total === 0)) {
    return <MarketEmpty closed={closed} filters={filters} onClear={onClear} />
  }
  if (!items.length) {
    return <div className="tenant-shelf__empty"><p>没有更多了</p></div>
  }
  return (
    <>
      <div className="tenant-shelf__grid">
        {items.map((item) => (
          <ShelfCard
            key={`${item.asset_type}-${item.name}`}
            item={item}
            canSubscribe={canSubscribe}
            onSubscribe={onSubscribe}
          />
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

const TenantShelf: React.FC<Props> = ({ canSubscribe, onSubscribe }) => {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const rawType = searchParams.get('type')
  const resolved = useMemo(() => resolveType(rawType), [rawType])
  const q = searchParams.get('q') || ''
  const host = searchParams.get('host') || ''
  const category = searchParams.get('category') || ''
  const page = Math.max(1, Number.parseInt(searchParams.get('page') || '1', 10) || 1)
  const [draftQ, setDraftQ] = useState(q)
  const [draftCat, setDraftCat] = useState(category)
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

  return (
    <div className="tenant-shelf" data-testid="tenant-shelf">
      <h1 className="tenant-shelf__heading">能力市场</h1>
      {resolved.illegal ? (
        <div className="tenant-shelf__empty"><p>没有这种类型</p></div>
      ) : (
        <>
          <Tabs
            activeKey={resolved.key}
            onChange={(key) => patchParams({ type: key === 'all' ? '' : key })}
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
            onPage={onPage}
            onClear={() => navigate('/capabilities')}
            canSubscribe={canSubscribe}
            onSubscribe={onSubscribe}
          />
        </>
      )}
    </div>
  )
}

export default TenantShelf
