/**
 * T-10（FR-05）：资产详情抽屉。公开详情 payload 是唯一数据源（AD-5）：
 * icon/背景（真图或 AssetVisual 占位）、能力标签、「帮你做的事」示例区
 * （未维护整体隐藏，附加 d）、md 正文（MarkdownBody，默认禁 raw HTML）、
 * 订阅 CTA 闸语义（闸关=禁用+钉句，附加 e）。预览态 unlisted 附「未上架」标记（OQ-D1）。
 * 只读 + 订阅：治理写操作在屏 4 治理表格行（读写分离，edge-states §5.4）。
 */
import React, { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button, Drawer, Skeleton, Tag, Typography, message } from 'antd'
import { CloseOutlined, CopyOutlined } from '@ant-design/icons'

import { fetchPublicCapability, type PublicCapabilityCard } from '../../services/capabilities'
import { READONLY_SUBSCRIBE, cardTitle, typeLabelOf } from './shelfCopy'
import AssetVisual, { visualIndex } from './AssetVisual'
import MarkdownBody from './MarkdownBody'
import './AssetDetailDrawer.css'

const { Paragraph, Text } = Typography

export const DRAWER_DETAIL_FAIL = '详情加载失败，请重试'
export const DRAWER_EMPTY_MD = '暂无正文'
export const DRAWER_EMPTY_MD_HINT = '该资产没有可展示的 Markdown 正文'
export const DRAWER_GATE_CLOSED = '市场暂未开放，开放后可订阅'
export const EXAMPLES_TITLE = '帮你做的事'
export const COPIED_TOAST = '已复制到剪贴板'

type Props = {
  open: boolean
  assetType: string
  name: string
  canSubscribe: boolean
  onSubscribe: (type: string, name: string) => void
  onClose: () => void
}

const mdBodyOf = (data: PublicCapabilityCard | undefined): string => {
  if (!data) return ''
  return data.skill_md || data.body_md || data.persona_md || ''
}

const formatDate = (raw?: string | null): string => {
  const day = (raw || '').slice(0, 10)
  return /^\d{4}-\d{2}-\d{2}$/.test(day) ? `更新于 ${day}` : ''
}

const AssetDetailDrawer: React.FC<Props> = ({
  open, assetType, name, canSubscribe, onSubscribe, onClose,
}) => {
  const query = useQuery({
    queryKey: ['admin', 'public-capability-detail', assetType, name],
    queryFn: () => fetchPublicCapability(assetType, name),
    enabled: open && Boolean(assetType) && Boolean(name),
    retry: false,
  })

  // 网络级失败：关闭抽屉 + 钉句 toast（edge-states §5.3；重试 = 重新点卡打开）
  useEffect(() => {
    if (open && query.isError) {
      onClose()
      message.error(DRAWER_DETAIL_FAIL)
    }
  }, [open, query.isError, onClose])

  const data = query.data
  const title = cardTitle({ title: data?.title, name })
  const gateClosed = data?.gate_open === false || data?.market_closed === true
  const unlistedPreview = data?.preview === true && data?.listing_state === 'unlisted'
  const examples = (data?.examples || []).filter((s) => s.trim().length > 0)
  const md = mdBodyOf(data)

  const copyExample = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      message.success(COPIED_TOAST)
    } catch {
      message.error('复制失败，请手动选择复制')
    }
  }

  const tags: Array<{ key: string; label: string; color?: string }> = [
    { key: 'type', label: typeLabelOf(assetType) },
  ]
  if (data?.featured) tags.push({ key: 'featured', label: '精选' })
  if (data?.listing_state === 'coming_soon') tags.push({ key: 'soon', label: '预告', color: 'processing' })
  if (unlistedPreview) tags.push({ key: 'unlisted', label: '未上架', color: 'warning' })
  if (data?.category) tags.push({ key: 'category', label: data.category })
  const shownTags = tags.slice(0, 6)
  const hiddenCount = tags.length - shownTags.length

  return (
    <Drawer
      title="资产详情"
      open={open}
      onClose={onClose}
      size={520}
      destroyOnHidden
      closeIcon={<span aria-label="关闭详情"><CloseOutlined /></span>}
      footer={
        <Button
          type="primary"
          block
          disabled={gateClosed || !canSubscribe}
          title={gateClosed ? DRAWER_GATE_CLOSED : (!canSubscribe ? READONLY_SUBSCRIBE : undefined)}
          onClick={() => { if (!gateClosed && canSubscribe) onSubscribe(assetType, name) }}
        >
          {gateClosed ? DRAWER_GATE_CLOSED : '订阅'}
        </Button>
      }
    >
      {query.isLoading || !data ? (
        <div data-testid="drawer-skeleton" aria-busy="true">
          <Skeleton.Node active style={{ width: '100%', height: 120 }} />
          <div style={{ display: 'flex', gap: 12, marginTop: 12, alignItems: 'center' }}>
            <Skeleton.Node active style={{ width: 72, height: 72 }} />
            <Skeleton active title paragraph={{ rows: 1 }} />
          </div>
          <Skeleton active title={false} paragraph={{ rows: 3 }} style={{ marginTop: 16 }} />
        </div>
      ) : (
        <div className="asset-drawer" data-testid="asset-drawer">
          <div
            className={`asset-drawer__banner${data.background ? '' : ` asset-visual--grad-${visualIndex(assetType, name)}`}`}
            style={data.background ? { backgroundImage: `url(${data.background})` } : undefined}
          />
          <div className="asset-drawer__head">
            <AssetVisual
              assetType={assetType}
              name={name}
              title={data.title}
              logo={data.logo}
              size="drawer"
            />
            <div className="asset-drawer__head-text">
              <Paragraph className="asset-drawer__title" ellipsis={{ rows: 2 }} title={title}>
                {title}
              </Paragraph>
              <Text type="secondary" className="asset-drawer__subtitle">
                {data.origin_plugin_name || typeLabelOf(assetType)}
              </Text>
              <Text type="secondary" className="asset-drawer__meta">
                {data.install_count != null && data.install_count >= 1
                  ? `已订阅 ${data.install_count.toLocaleString('zh-Hans')} 次` : null}
                {data.install_count != null && data.install_count >= 1 && data.updated_at ? ' · ' : null}
                {formatDate(data.updated_at)}
              </Text>
            </div>
          </div>
          <div className="asset-drawer__tags">
            {shownTags.map((t) => <Tag key={t.key} color={t.color}>{t.label}</Tag>)}
            {hiddenCount > 0 ? <Tag title={tags.map((t) => t.label).join(' / ')}>+{hiddenCount}</Tag> : null}
          </div>
          {examples.length > 0 ? (
            <section className="asset-drawer__examples" aria-label={EXAMPLES_TITLE}>
              <Text strong>{EXAMPLES_TITLE}</Text>
              {examples.map((example, i) => (
                <blockquote key={`${i}-${example.slice(0, 12)}`} className="asset-drawer__example">
                  <span>{example}</span>
                  <Button
                    size="small"
                    icon={<CopyOutlined />}
                    aria-label="复制这条示例"
                    onClick={() => { void copyExample(example) }}
                  />
                </blockquote>
              ))}
            </section>
          ) : null}
          <div className="asset-drawer__body">
            {md ? <MarkdownBody md={md} /> : (
              <div className="asset-drawer__empty-md" data-testid="drawer-empty-md">
                <p>{DRAWER_EMPTY_MD}</p>
                <Text type="secondary">{DRAWER_EMPTY_MD_HINT}</Text>
              </div>
            )}
          </div>
        </div>
      )}
    </Drawer>
  )
}

export default AssetDetailDrawer
