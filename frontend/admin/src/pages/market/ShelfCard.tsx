/**
 * T-08（FR-03 / NFR-U1）：货架卡片四要素——① icon 头像（真图/AssetVisual 占位）
 * ② 主标题 + 副标题（origin_plugin_name 无则类型中文兜底）③ ≤2 行描述（缺失=暂无描述）
 * ④ 底部标签 ≤3（精选 > 预告 > 类型 > 其他，超出 +N）。整卡可点开详情抽屉。
 * 订阅按钮已按 designer 裁定移除（edge-states §1.2：CTA 收敛抽屉，一屏一个主行动）。
 */
import React from 'react'
import { Tag, Typography } from 'antd'

import type { PublicShelfItem } from '../../services/capabilities'
import { NO_DESC, cardTitle, typeLabelOf } from './shelfCopy'
import AssetVisual, { visualIndex } from './AssetVisual'

const { Paragraph } = Typography

const cardTags = (item: PublicShelfItem): Array<{ key: string; label: string; color?: string }> => {
  const tags: Array<{ key: string; label: string; color?: string }> = []
  if (item.featured) tags.push({ key: 'featured', label: '精选' })
  if (item.listing_state === 'coming_soon') {
    tags.push({ key: 'soon', label: '预告', color: 'processing' })
  }
  tags.push({ key: 'type', label: typeLabelOf(item.asset_type) })
  if (item.category) tags.push({ key: 'category', label: item.category })
  return tags
}

const ShelfCard: React.FC<{ item: PublicShelfItem; onOpen: (item: PublicShelfItem) => void }> = ({
  item, onOpen,
}) => {
  const title = cardTitle(item)
  const tags = cardTags(item)
  const shown = tags.slice(0, 3)
  const hidden = tags.length - shown.length
  const bannerStyle = item.background
    ? { backgroundImage: `url(${item.background})` }
    : undefined
  return (
    <button
      type="button"
      className="shelf-card"
      aria-label={`查看 ${title} 详情`}
      onClick={() => onOpen(item)}
    >
      <span
        aria-hidden="true"
        className={`shelf-card__banner${item.background ? '' : ` asset-visual--grad-${visualIndex(item.asset_type, item.name)}`}`}
        style={bannerStyle}
      />
      <span className="shelf-card__head">
        <AssetVisual
          assetType={item.asset_type}
          name={item.name}
          title={item.title}
          logo={item.logo}
          size="card"
        />
        <span className="shelf-card__titles">
          <span className="shelf-card__title" title={title}>{title}</span>
          <span className="shelf-card__subtitle">
            {item.origin_plugin_name || typeLabelOf(item.asset_type)}
          </span>
        </span>
      </span>
      <Paragraph
        className="shelf-card__desc"
        type="secondary"
        ellipsis={{ rows: 2 }}
      >
        {item.description?.trim() || NO_DESC}
      </Paragraph>
      <span className="shelf-card__tags">
        {shown.map((t) => <Tag key={t.key} color={t.color}>{t.label}</Tag>)}
        {hidden > 0 ? <Tag title={tags.map((t) => t.label).join(' / ')}>+{hidden}</Tag> : null}
      </span>
    </button>
  )
}

export default ShelfCard
