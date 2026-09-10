/**
 * 首页·能力精选：公开列表最多 6 张真卡。
 * 列表失败 ≠ 空：GWT-01.4 文案「暂时无法加载能力」+「重试」。
 */
import React from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { TIER_COLORS } from '@auto-agents/frontend-shared'
import { Button, Card, Skeleton, Tag, Typography } from 'antd'
import { ArrowRightOutlined } from '@ant-design/icons'

import { listPublicSkills, type PublicSkill } from '../../services/skills'
import { FadeIn, SectionTitle } from './common'

const { Paragraph, Text } = Typography

const FEATURED_LIMIT = 6

const pickFeatured = (items: PublicSkill[]): PublicSkill[] => {
  const featured = items.filter(
    (s) => s.tier === 'S' || s.tier === 'A' || s.status === 'recommended',
  )
  return (featured.length > 0 ? featured : items).slice(0, FEATURED_LIMIT)
}

const SkillsSection: React.FC = () => {
  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['official', 'public-skills-featured'],
    queryFn: () => listPublicSkills({ page: 1, page_size: 50 }),
  })

  const items = data ? pickFeatured(data.items) : []
  const retrying = isFetching && !isLoading

  return (
    <section id="skills" style={{ padding: '72px 0', background: 'var(--color-surface-sunken)' }}>
      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '0 24px' }}>
        <FadeIn>
          <SectionTitle
            eyebrow="CAPABILITIES"
            title="能力精选"
            description="已上架的可复用能力，可在能力市场查看详情。"
          />
        </FadeIn>

        {isLoading && (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
              gap: 20,
              marginTop: 32,
            }}
          >
            {Array.from({ length: FEATURED_LIMIT }).map((_, idx) => (
              <Card key={`featured-skel-${idx}`}>
                <Skeleton active paragraph={{ rows: 2 }} />
              </Card>
            ))}
          </div>
        )}

        {isError && (
          <div role="alert" style={{ textAlign: 'center', marginTop: 32 }}>
            <p style={{ fontSize: 16, marginBottom: 16 }}>暂时无法加载能力</p>
            <Button
              type="primary"
              autoInsertSpace={false}
              onClick={() => {
                void refetch()
              }}
              loading={retrying}
            >
              {retrying ? '重试中…' : '重试'}
            </Button>
          </div>
        )}

        {!isLoading && !isError && items.length === 0 && (
          <div style={{ textAlign: 'center', marginTop: 32 }}>
            <p style={{ fontSize: 16, marginBottom: 16 }}>
              还没有上架的能力。开通后可在能力市场浏览。
            </p>
            <Link to="/capabilities">去能力市场</Link>
          </div>
        )}

        {!isLoading && !isError && items.length > 0 && (
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
                <Link
                  to={`/capabilities?type=skill&q=${encodeURIComponent(skill.name)}`}
                  style={{ textDecoration: 'none', color: 'inherit', display: 'block' }}
                >
                  <Card style={{ height: '100%' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Text strong style={{ fontSize: 16 }}>{skill.title || skill.name}</Text>
                      {skill.status === 'coming_soon' && <Tag>预告</Tag>}
                      {skill.tier && skill.status !== 'coming_soon' && (
                        <Tag color={TIER_COLORS[skill.tier]}>{skill.tier}</Tag>
                      )}
                    </div>
                    <Paragraph type="secondary" ellipsis={{ rows: 2 }} style={{ marginTop: 8, minHeight: 44 }}>
                      {skill.description || '（暂无描述）'}
                    </Paragraph>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Tag>{skill.category}</Tag>
                      <Text type="secondary">
                        {skill.score != null ? `${skill.score.toFixed(1)} 分` : '评审中'}
                      </Text>
                    </div>
                  </Card>
                </Link>
              </FadeIn>
            ))}
          </div>
        )}

        <FadeIn delay={0.2}>
          <div style={{ textAlign: 'center', marginTop: 32 }}>
            <Link to="/capabilities" style={{ fontSize: 16, color: 'var(--site-primary)' }}>
              去能力市场 <ArrowRightOutlined />
            </Link>
          </div>
        </FadeIn>
      </div>
    </section>
  )
}

export default SkillsSection
