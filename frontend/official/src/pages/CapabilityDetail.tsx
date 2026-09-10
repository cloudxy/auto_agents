/**
 * 能力市场详情（T-24）：不可信正文纯文本；出处仅父已上架才给商店链接。
 */
import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { Button, Skeleton, Tag } from 'antd'

import {
  getPublicAsset,
  type PublicAssetDetail,
  type PublicOrigin,
} from '../services/capabilities'
import { displaySlash } from './capabilityMarket'
import NotFound from './NotFound'
import './CapabilityDetail.css'

const PUBLIC_TYPES = new Set(['skill', 'plugin', 'command', 'agent', 'team'])
const LEGACY: Record<string, string> = { expert: 'agent', expert_team: 'team' }

function adminBaseUrl(): string {
  return (process.env.REACT_APP_ADMIN_URL || '').replace(/\/$/, '')
}

function subscribeLoginHref(type: string, name: string): string | null {
  const admin = adminBaseUrl()
  if (!admin) return null
  const bounce = new URLSearchParams({ subscribeType: type, subscribeName: name })
  bounce.set('from', `/capabilities?${bounce.toString()}`)
  return `${admin}/login?${bounce.toString()}`
}

function httpStatus(error: unknown): number | undefined {
  if (typeof error !== 'object' || error === null) return undefined
  return (error as { response?: { status?: number } }).response?.status
}

function isStoreNotFound(error: unknown): boolean {
  return httpStatus(error) === 404
}

function resolveType(raw: string | undefined): string | null {
  if (!raw) return null
  if (PUBLIC_TYPES.has(raw)) return raw
  return LEGACY[raw] ?? null
}

function originStoreHref(origin: PublicOrigin | null | undefined): string | null {
  const href = origin?.href
  if (!href || typeof href !== 'string') return null
  if (!href.startsWith('/capabilities/') || href.startsWith('//')) return null
  return href
}

function originLabel(detail: PublicAssetDetail): string {
  const origin = detail.origin
  return origin?.title || origin?.name || detail.origin_plugin_name || detail.source_author || ''
}

const OriginCredit: React.FC<{ detail: PublicAssetDetail }> = ({ detail }) => {
  const label = originLabel(detail)
  if (!label) return null
  const href = originStoreHref(detail.origin)
  return (
    <div data-testid="origin" className="capability-detail__origin">
      <span className="capability-detail__label">出处</span>
      {href ? <Link to={href}>{label}</Link> : <span>{label}</span>}
    </div>
  )
}

const IncludesList: React.FC<{ detail: PublicAssetDetail }> = ({ detail }) => {
  const items = detail.includes || []
  if (!items.length) return null
  return (
    <section className="capability-detail__includes">
      <h2>包含</h2>
      <ul>
        {items.map((item) => (
          <li key={`${item.asset_type}-${item.name}`}>
            <Link
              to={`/capabilities/${encodeURIComponent(item.asset_type)}/${encodeURIComponent(item.name)}`}
            >
              {item.title || item.name}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}

const SubscribeCta: React.FC<{ detail: PublicAssetDetail; offline: boolean }> = ({
  detail, offline,
}) => {
  if (detail.listing_state === 'coming_soon' || detail.subscribable === false) return null
  const href = subscribeLoginHref(detail.asset_type, detail.name)
  if (!href) return null
  if (offline) {
    return <Button type="primary" disabled autoInsertSpace={false}>网络不可用，现在不能订阅。</Button>
  }
  return <a className="capability-detail__subscribe" href={href}>登录后订阅</a>
}

const DetailSkeleton: React.FC = () => (
  <div className="capability-detail" data-testid="capability-detail-skeleton" aria-busy="true">
    <Skeleton active title={{ width: '40%' }} paragraph={{ rows: 2 }} />
    <div className="capability-detail__body-skel" />
  </div>
)

const DetailError: React.FC<{
  offline: boolean
  onRetry: () => void
  retrying: boolean
}> = ({ offline, onRetry, retrying }) => {
  const title = offline
    ? '打不开这份说明：网络不可用。连接恢复后重试。'
    : '能力详情加载失败。检查网络后重试。'
  return (
    <div className="capability-detail" role="alert">
      <p>{title}</p>
      <Button type="primary" onClick={onRetry} loading={retrying} autoInsertSpace={false}>
        重试
      </Button>
    </div>
  )
}

const HostsAndLicense: React.FC<{ detail: PublicAssetDetail }> = ({ detail }) => (
  <dl className="capability-detail__meta">
    {detail.license ? <><dt>许可</dt><dd>{detail.license}</dd></> : null}
    {detail.hosts?.length ? (
      <><dt>宿主</dt><dd>{detail.hosts.map((host) => <Tag key={host}>{host}</Tag>)}</dd></>
    ) : null}
    {detail.source_url?.startsWith('http') ? (
      <><dt>来源</dt><dd><a href={detail.source_url} rel="noreferrer noopener">{detail.source_url}</a></dd></>
    ) : null}
  </dl>
)

const DetailView: React.FC<{
  detail: PublicAssetDetail
  offline: boolean
  refreshing: boolean
}> = ({ detail, offline, refreshing }) => {
  const slash = displaySlash(detail.slash)
  return (
  <article className={refreshing ? 'capability-detail capability-detail--refreshing' : 'capability-detail'}>
    <p><Link to="/capabilities">返回市场</Link></p>
    <header>
      <h1>{detail.title || detail.name}</h1>
      {detail.listing_state === 'coming_soon' ? <span className="capability-detail__soon">预告</span> : null}
      {slash ? <p data-testid="command-slash" className="capability-detail__slash">{slash}</p> : null}
      <p className="capability-detail__slug">{detail.name}</p>
    </header>
    <HostsAndLicense detail={detail} />
    <OriginCredit detail={detail} />
    <section>
      <h2>说明</h2>
      <p>{detail.description || '（暂无描述）'}</p>
    </section>
    <pre data-testid="skill-md" tabIndex={0} className="capability-detail__body">
      {detail.skill_md ?? detail.body_md ?? ''}
    </pre>
    <IncludesList detail={detail} />
    <SubscribeCta detail={detail} offline={offline} />
    <p className="capability-detail__note">订阅不等于已在宿主运行</p>
  </article>
  )
}

const CapabilityDetail: React.FC = () => {
  const { type, slug } = useParams<{ type: string; slug: string }>()
  const publicType = resolveType(type)
  const offline = typeof navigator !== 'undefined' && navigator.onLine === false
  const query = useQuery({
    queryKey: ['official', 'public-capability', publicType, slug],
    queryFn: () => getPublicAsset(publicType as string, slug as string),
    enabled: Boolean(publicType && slug),
    retry: false,
  })

  if (!publicType || !slug) return <NotFound />
  if (query.isLoading) return <DetailSkeleton />
  if (query.isError) {
    if (isStoreNotFound(query.error)) return <NotFound />
    return (
      <DetailError
        offline={offline}
        onRetry={() => { void query.refetch() }}
        retrying={query.isFetching}
      />
    )
  }
  if (!query.data) return <NotFound />
  return (
    <DetailView
      detail={query.data}
      offline={offline}
      refreshing={query.isFetching && !query.isLoading}
    />
  )
}

export default CapabilityDetail
