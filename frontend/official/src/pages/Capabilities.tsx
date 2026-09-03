/**
 * 能力广场页（P6 C9）：四类资产公开浏览（skill/plugin/expert/expert_team）
 */
import React, { useEffect, useState } from 'react'
import { TIER_COLORS, ASSET_TYPE_LABELS as TYPE_LABELS, type PublicAsset } from '@auto-agents/frontend-shared'
import { Card, Empty, Spin, Tabs, Tag, Typography } from 'antd'
import { listPublicAssets } from '../services/capabilities'


const { Text, Paragraph } = Typography


const listPublic = (type: string): Promise<{ items: PublicAsset[] }> => listPublicAssets(type)

const AssetGrid: React.FC<{ type: string }> = ({ type }) => {
  const [items, setItems] = useState<PublicAsset[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    listPublic(type).then((d) => setItems(d.items || [])).catch(() => setItems([]))
      .finally(() => setLoading(false))
  }, [type])

  if (loading) return <div style={{ textAlign: 'center', padding: 64 }}><Spin /></div>
  if (!items.length) return <Empty description={`暂无已发布${TYPE_LABELS[type]}`} style={{ padding: 64 }} />

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 16 }}>
      {items.map((a) => (
        <Card key={a.name} hoverable>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <Text strong>{a.title || a.name}</Text>
            {a.tier && <Tag color={TIER_COLORS[a.tier]}>{a.tier}</Tag>}
          </div>
          <Paragraph type="secondary" ellipsis={{ rows: 2 }} style={{ marginTop: 6 }}>
            {a.description || '（暂无描述）'}
          </Paragraph>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <Tag>{a.category}</Tag>
            <Text type="secondary">{a.score != null ? `${a.score.toFixed(1)} 分` : '评审中'}</Text>
          </div>
        </Card>
      ))}
    </div>
  )
}

const Capabilities: React.FC = () => (
  <div style={{ minHeight: '100vh', background: '#f7f9fc' }}>
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: '24px 24px 64px' }}>
      <Tabs items={[
        { key: 'skill', label: '技能', children: <AssetGrid type="skill" /> },
        { key: 'plugin', label: '插件', children: <AssetGrid type="plugin" /> },
        { key: 'expert', label: '专家', children: <AssetGrid type="expert" /> },
        { key: 'expert_team', label: '专家团', children: <AssetGrid type="expert_team" /> },
      ]} />
    </div>
  </div>
)

export default Capabilities
