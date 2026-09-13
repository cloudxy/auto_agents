/**
 * 能力市场列表（T-22）：筛选项进 URL；失败≠空；预告无订阅按钮。
 */
import React, { useEffect, useMemo, useState } from 'react'
import { TIER_COLORS } from '@auto-agents/frontend-shared'
import { useQuery } from '@tanstack/react-query'
import { Button, Card, Input, Select, Skeleton, Tabs, Tag, Typography } from 'antd'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'

import { listPublicAssets, type PublicListItem } from '../services/capabilities'
import {
  EMPTY_SHELF,
  EMPTY_SHELF_HINT,
  FILTER_EMPTY,
  HOST_OPTIONS,
  LEGACY_MAP,
  LOAD_FAIL,
  LOAD_FAIL_HINT,
  MARKET_CLOSED,
  MARKET_CLOSED_HINT,
  PUBLIC_TYPES,
  TYPE_LABELS,
  activeFilterEcho,
  cardTitle,
  displaySlash,
  hasActiveFilters,
  resolveType,
  type MarketFilterValues,
} from './capabilityMarket'
import './Capabilities.css'

const { Paragraph, Text } = Typography

type FilterPatch = Record<string, string>

const MarketSkeleton: React.FC = () => (
  <div className="capability-market__grid" data-testid="market-skeleton" aria-busy="true">
    {Array.from({ length: 6 }, (_, i) => (
      <div key={i} className="capability-market__skel">
        <Skeleton active title paragraph={{ rows: 3 }} />
      </div>
    ))}
  </div>
)

const MarketError: React.FC<{ onRetry: () => void; retrying: boolean }> = ({
  onRetry, retrying,
}) => (
  <div className="capability-market__error" role="alert">
    <p>{LOAD_FAIL}</p>
    <p>{LOAD_FAIL_HINT}</p>
    <Button type="primary" onClick={onRetry} loading={retrying} autoInsertSpace={false}>
      重试
    </Button>
  </div>
)

const FilterEcho: React.FC<{ filters: MarketFilterValues }> = ({ filters }) => (
  <ul data-testid="filter-echo" className="capability-market__echo">
    {activeFilterEcho(filters).map((row) => (
      <li key={row.key}>{`${row.label}：${row.value}`}</li>
    ))}
  </ul>
)

const MarketEmpty: React.FC<{
  closed: boolean
  filters: MarketFilterValues
  onClear: () => void
}> = ({ closed, filters, onClear }) => {
  const filtered = hasActiveFilters(filters)
  if (closed) {
    return (
      <div className="capability-market__empty" data-testid="market-closed">
        <p>{MARKET_CLOSED}</p>
        <p>{MARKET_CLOSED_HINT}</p>
        <Link to="/">返回首页</Link>
      </div>
    )
  }
  return (
    <div className="capability-market__empty" data-testid={filtered ? 'filter-empty' : 'empty-shelf'}>
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
          <a href="#capability-filters">了解类型</a>
        </>
      )}
    </div>
  )
}

const MarketCard: React.FC<{ item: PublicListItem }> = ({ item }) => {
  const title = cardTitle(item)
  const href = `/capabilities/${encodeURIComponent(item.asset_type)}/${encodeURIComponent(item.name)}`
  const soon = item.listing_state === 'coming_soon'
  const slash = item.asset_type === 'command' ? displaySlash(item.slash) : null
  return (
    <Link to={href} aria-label={title} className="capability-market__card-link">
      <Card hoverable className="capability-market__card">
        <div className="capability-market__card-head">
          <span className="capability-market__title">{title}</span>
          {soon ? <span className="capability-market__soon">预告</span> : null}
          {item.tier ? <Tag color={TIER_COLORS[item.tier]}>{item.tier}</Tag> : null}
        </div>
        {slash ? <span data-testid="command-slash" className="capability-market__slash">{slash}</span> : null}
        <Paragraph type="secondary" ellipsis={{ rows: 2 }} className="capability-market__desc">
          {item.description || '（暂无描述）'}
        </Paragraph>
        <div className="capability-market__meta">
          <Tag>{TYPE_LABELS[item.asset_type] || item.category}</Tag>
          <Text type="secondary">{item.score != null ? `${item.score.toFixed(1)} 分` : '评审中'}</Text>
        </div>
      </Card>
    </Link>
  )
}

const MarketPager: React.FC<{
  page: number
  total: number
  hasMore: boolean
  onPage: (page: number) => void
}> = ({ page, total, hasMore, onPage }) => {
  if (total <= 0) return null // GWT-81.3：0 件不出现翻页数字谎称有货
  return (
    <nav className="capability-market__pager" data-testid="market-pager" aria-label="翻页">
      <span className="capability-market__pager-total">共 {total} 件</span>
      <span className="capability-market__pager-current">第 {page} 页</span>
      {page > 1 ? (
        <Button onClick={() => onPage(page - 1)} autoInsertSpace={false}>上一页</Button>
      ) : null}
      {/* GWT-81.2：has_more 为假时不渲染下一页（无假控件带向空货架） */}
      {hasMore ? (
        <Button type="primary" onClick={() => onPage(page + 1)} autoInsertSpace={false}>
          下一页
        </Button>
      ) : null}
    </nav>
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
}> = ({ type, q, host, category, page, onPage, onClear }) => {
  const typeParam = type === 'all' ? undefined : type
  const filters: MarketFilterValues = { type, q, host, category }
  const query = useQuery({
    queryKey: ['official', 'public-capabilities', typeParam, q, host, category, page],
    queryFn: () => listPublicAssets({
      type: typeParam,
      q: q || undefined,
      host: host || undefined,
      category: category || undefined,
      page,
    }),
    retry: false,
  })
  if (query.isLoading) return <MarketSkeleton />
  if (query.isError) {
    return (
      <MarketError
        onRetry={() => { void query.refetch() }}
        retrying={query.isFetching}
      />
    )
  }
  const items = query.data?.items || []
  const total = query.data?.total ?? 0
  const hasMore = query.data?.has_more === true
  const closed = query.data?.market_closed === true
  const pager = <MarketPager page={page} total={total} hasMore={hasMore} onPage={onPage} />
  if (closed || (!items.length && total === 0)) {
    return <MarketEmpty closed={closed} filters={filters} onClear={onClear} />
  }
  if (!items.length) {
    // 深链越过末页：不把空页谎称为空货架句
    return (
      <>
        <div className="capability-market__empty"><p>没有更多了</p></div>
        {pager}
      </>
    )
  }
  const refreshing = query.isFetching && !query.isLoading
  return (
    <>
      {refreshing ? <div className="capability-market__progress" /> : null}
      <div className={refreshing ? 'capability-market__grid capability-market__grid--refreshing' : 'capability-market__grid'}>
        {items.map((item) => (
          <MarketCard key={`${item.asset_type}-${item.name}`} item={item} />
        ))}
      </div>
      {pager}
    </>
  )
}

const FilterBar: React.FC<{
  q: string; host: string; category: string; onPatch: (partial: FilterPatch) => void
}> = ({ q, host, category, onPatch }) => {
  const [draftQ, setDraftQ] = useState(q)
  const [draftCat, setDraftCat] = useState(category)
  useEffect(() => { setDraftQ(q) }, [q])
  useEffect(() => { setDraftCat(category) }, [category])
  return (
    <div id="capability-filters" className="capability-market__filters">
      <Input.Search
        allowClear
        enterButton={<Button type="primary" autoInsertSpace={false}>搜索</Button>}
        placeholder="展示名或短名"
        value={draftQ}
        onChange={(e) => setDraftQ(e.target.value)}
        onSearch={(value) => onPatch({ q: value })}
        aria-label="搜索能力"
      />
      <Select
        allowClear
        className="capability-market__host"
        aria-label="宿主"
        placeholder="宿主"
        value={host || undefined}
        options={[...HOST_OPTIONS]}
        onChange={(value) => onPatch({ host: value || '' })}
      />
      <Input
        allowClear
        className="capability-market__category"
        aria-label="分类"
        placeholder="分类"
        value={draftCat}
        onChange={(e) => setDraftCat(e.target.value)}
        onPressEnter={(e) => onPatch({ category: e.currentTarget.value })}
        onBlur={(e) => onPatch({ category: e.currentTarget.value })}
      />
    </div>
  )
}

function writeParams(
  prev: URLSearchParams,
  patch: FilterPatch,
): URLSearchParams {
  const next = new URLSearchParams(prev)
  Object.entries(patch).forEach(([key, value]) => {
    const trimmed = value.trim()
    if (!trimmed) next.delete(key)
    else next.set(key, trimmed)
  })
  return next
}

function useMarketFilters() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const pathIsSkills = pathname === '/skills'
  const rawType = searchParams.get('type')
  const resolved = useMemo(
    () => resolveType(rawType, pathIsSkills),
    [rawType, pathIsSkills],
  )
  const page = Math.max(1, Number.parseInt(searchParams.get('page') || '1', 10) || 1)
  useEffect(() => {
    if (!rawType || !LEGACY_MAP[rawType]) return
    setSearchParams((prev) => writeParams(prev, { type: LEGACY_MAP[rawType] }), { replace: true })
  }, [rawType, setSearchParams])
  const patchParams = (partial: FilterPatch) => {
    setSearchParams((prev) => {
      const next = writeParams(prev, partial)
      if (!('page' in partial)) next.delete('page') // 筛选变化回第 1 页
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
  const onTab = (key: string) => patchParams({ type: key === 'all' ? '' : key })
  return {
    resolved,
    q: searchParams.get('q') || '',
    host: searchParams.get('host') || '',
    category: searchParams.get('category') || '',
    page,
    patchParams,
    onTab,
    onPage,
    onClear: () => navigate('/capabilities'),
  }
}

const Capabilities: React.FC = () => {
  const market = useMarketFilters()
  return (
    <div className="capability-market">
      <div className="capability-market__inner">
        <h1>能力市场</h1>
        {market.resolved.illegal ? (
          <div className="capability-market__illegal">
            <p>没有这种类型</p>
            <p>请选择技能、插件、命令、智能体或专家团。</p>
          </div>
        ) : (
          <>
            <Tabs
              activeKey={market.resolved.key}
              onChange={market.onTab}
              items={[
                { key: 'all', label: '全部' },
                ...PUBLIC_TYPES.map((t) => ({ key: t.key, label: t.label })),
              ]}
            />
            <FilterBar
              q={market.q}
              host={market.host}
              category={market.category}
              onPatch={market.patchParams}
            />
            <AssetGrid
              type={market.resolved.key}
              q={market.q}
              host={market.host}
              category={market.category}
              page={market.page}
              onPage={market.onPage}
              onClear={market.onClear}
            />
          </>
        )}
      </div>
    </div>
  )
}

export default Capabilities
