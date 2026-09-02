/**
 * 能力广场页（P6 C9）：四类资产公开浏览（skill/plugin/expert/expert_team）
 */
import React, { useCallback, useEffect, useState } from 'react'
import { Card, Empty, Spin, Tabs, Tag, Typography } from 'antd'

import api from '../services/api'

const { Text, Paragraph } = Typography

interface PublicAsset {
  asset_type: string
  name: string
  title: string
  description?: string | null
  category: string
  tier?: string | null
  score?: number | null
}

const TIER_COLORS: Record<string, string> = { S: 'gold', A: 'green', B: 'blue', C: 'default' }

const TYPE_LABELS: Record<string, string> = {
  skill: '技能', plugin: '插件', expert: '专家', expert_team: '专家团',
}

const listPublic = (type: string): Promise<{ items: PublicAsset[] }> =>
  api.get('/public/capabilities', { params: { type, page_size: 50 } })
    .then((r) => (r as unknown as { data: { items: PublicAsset[] } }).data)

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
    <div style={{ background: '#001529', padding: '14px 24px', display: 'flex',
                 justifyContent: 'space-between', alignItems: 'center' }}>
      <a href="/" style={{ color: '#fff', fontSize: 18, fontWeight: 700 }}>AutoAgents</a>
      <Text style={{ color: 'rgba(255,255,255,0.65)' }}>能力广场</Text>
    </div>
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
