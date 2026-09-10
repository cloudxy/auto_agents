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
  HOST_OPTIONS,
  LEGACY_MAP,
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
    <p>市场列表加载失败</p>
    <p>检查网络后重试</p>
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

const MarketEmpty: React.FC<{ filters: MarketFilterValues; onClear: () => void }> = ({
  filters, onClear,
}) => {
  const filtered = hasActiveFilters(filters)
  return (
    <div className="capability-market__empty">
      {filtered ? (
        <>
          <p>没有符合条件的能力</p>
          <FilterEcho filters={filters} />
          <Button onClick={onClear} autoInsertSpace={false}>清除筛选</Button>
        </>
      ) : (
        <>
          <p>还没有上架的能力</p>
          <p>已上架且过许可的能力会出现在这里。</p>
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

const AssetGrid: React.FC<{
  type: string
  q: string
  host: string
  category: string
  onClear: () => void
}> = ({ type, q, host, category, onClear }) => {
  const typeParam = type === 'all' ? undefined : type
  const filters: MarketFilterValues = { type, q, host, category }
  const query = useQuery({
    queryKey: ['official', 'public-capabilities', typeParam, q, host, category],
    queryFn: () => listPublicAssets({
      type: typeParam,
      q: q || undefined,
      host: host || undefined,
      category: category || undefined,
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
  if (!items.length) return <MarketEmpty filters={filters} onClear={onClear} />
  const refreshing = query.isFetching && !query.isLoading
  return (
    <>
      {refreshing ? <div className="capability-market__progress" /> : null}
      <div className={refreshing ? 'capability-market__grid capability-market__grid--refreshing' : 'capability-market__grid'}>
        {items.map((item) => (
          <MarketCard key={`${item.asset_type}-${item.name}`} item={item} />
        ))}
      </div>
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
  useEffect(() => {
    if (!rawType || !LEGACY_MAP[rawType]) return
    setSearchParams((prev) => writeParams(prev, { type: LEGACY_MAP[rawType] }), { replace: true })
  }, [rawType, setSearchParams])
  const patchParams = (partial: FilterPatch) => {
    setSearchParams((prev) => writeParams(prev, partial), { replace: true })
  }
  const onTab = (key: string) => patchParams({ type: key === 'all' ? '' : key })
  return {
    resolved,
    q: searchParams.get('q') || '',
    host: searchParams.get('host') || '',
    category: searchParams.get('category') || '',
    patchParams,
    onTab,
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
              onClear={market.onClear}
            />
          </>
        )}
      </div>
    </div>
  )
}

export default Capabilities
