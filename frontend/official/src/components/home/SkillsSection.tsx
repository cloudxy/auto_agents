/**
 * 首页·技能广场板块（方案 A · A-P4-2）
 * 数据来自公开 API（真实数据，无需"示意"角标）；精选 tier=S/A 或 recommended 共 6 个。
 * 沿用 FeaturesSection 卡片范式 + common 的 FadeIn/SectionTitle。
 */
import React, { useEffect, useState } from 'react'
import { Card, Tag, Typography } from 'antd'
import { ArrowRightOutlined } from '@ant-design/icons'

import { listPublicSkills, type PublicSkill } from '../../services/skills'
import { FadeIn, SectionTitle } from './common'

const { Paragraph, Text } = Typography

const TIER_COLORS: Record<string, string> = { S: 'gold', A: 'green', B: 'blue', C: 'default' }

const SkillsSection: React.FC = () => {
  const [items, setItems] = useState<PublicSkill[]>([])

  useEffect(() => {
    listPublicSkills({ page: 1, page_size: 50 })
      .then((data) => {
        const featured = data.items
          .filter((s) => s.tier === 'S' || s.tier === 'A' || s.status === 'recommended')
          .slice(0, 6)
        setItems(featured.length > 0 ? featured : data.items.slice(0, 6))
      })
      .catch(() => setItems([])) // 公开板块：后端不可达时静默空态，不影响首页其余部分
  }, [])

  return (
    <section id="skills" style={{ padding: '72px 0', background: '#f7f9fc' }}>
      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '0 24px' }}>
        <FadeIn>
          <SectionTitle
            eyebrow="SKILLS"
            title="技能广场"
            description="平台沉淀的可复用 Agent 技能库——AI 评分 + 人工复核，建一次全 Agent 共用"
          />
        </FadeIn>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
            gap: 20,
            marginTop: 32,
          }}
        >
          {items.map((skill, idx) => (
            <FadeIn key={skill.name} delay={idx * 0.06}>
              <Card
                hoverable
                style={{ height: '100%' }}
                onClick={() => { window.location.href = `/skills?q=${encodeURIComponent(skill.name)}` }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Text strong style={{ fontSize: 16 }}>{skill.title || skill.name}</Text>
                  {skill.tier && <Tag color={TIER_COLORS[skill.tier]}>{skill.tier}</Tag>}
                </div>
                <Paragraph type="secondary" ellipsis={{ rows: 2 }} style={{ marginTop: 8, minHeight: 44 }}>
                  {skill.description || '（暂无描述）'}
                </Paragraph>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <Tag>{skill.category}</Tag>
                  <Text type="secondary">{skill.score != null ? `${skill.score.toFixed(1)} 分` : '评审中'}</Text>
                </div>
              </Card>
            </FadeIn>
          ))}
        </div>
        <FadeIn delay={0.2}>
          <div style={{ textAlign: 'center', marginTop: 32 }}>
            <a href="/skills" style={{ fontSize: 16, color: '#1677ff' }}>
              查看全部技能 <ArrowRightOutlined />
            </a>
          </div>
        </FadeIn>
      </div>
    </section>
  )
}

export default SkillsSection
