/**
 * 技能广场独立页（方案 A · A-P4-2）：分类筛选 + 搜索 + 卡片网格 + 详情展开。
 *
 * 安全约定：SKILL.md 为不可信内容，一律以纯文本渲染（React 文本节点自动转义，
 * 不走 markdown/HTML 注入路径）——XSS payload 只会成为可见文本。
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Card, Empty, Input, Layout, Menu, Spin, Tag, Typography } from 'antd'
import { SearchOutlined } from '@ant-design/icons'

import { getPublicSkill, listPublicSkills, type PublicSkill } from '../services/skills'

const { Text, Paragraph } = Typography

const TIER_COLORS: Record<string, string> = { S: 'gold', A: 'green', B: 'blue', C: 'default' }

const PAGE_SIZE = 60

const SkillsSquare: React.FC<{ initialQuery?: string }> = ({ initialQuery = '' }) => {
  const [items, setItems] = useState<PublicSkill[]>([])
  const [loading, setLoading] = useState(true)
  const [keyword, setKeyword] = useState(initialQuery)
  const [category, setCategory] = useState<string>('')
  const [detail, setDetail] = useState<PublicSkill | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const load = useCallback(async (q: string, cat: string) => {
    setLoading(true)
    try {
      const data = await listPublicSkills({ q: q || undefined, category: cat || undefined, page: 1, page_size: PAGE_SIZE })
      setItems(data.items)
    } catch {
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load(keyword, category) }, [load, keyword, category])  // eslint-disable-line react-hooks/exhaustive-deps

  const categories = useMemo(() => {
    const counter = new Map<string, number>()
    items.forEach((s) => counter.set(s.category, (counter.get(s.category) ?? 0) + 1))
    return Array.from(counter.entries()).sort((a, b) => b[1] - a[1])
  }, [items])

  const openDetail = async (name: string) => {
    setDetailLoading(true)
    try {
      setDetail(await getPublicSkill(name))
    } catch {
      setDetail(null)
    } finally {
      setDetailLoading(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: '#f7f9fc' }}>
      <div style={{ background: '#001529', padding: '14px 24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <a href="/" style={{ color: '#fff', fontSize: 18, fontWeight: 700 }}>AutoAgents</a>
        <Text style={{ color: 'rgba(255,255,255,0.65)' }}>技能广场</Text>
      </div>

      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '24px 24px 64px' }}>
        <Input
          size="large"
          prefix={<SearchOutlined />}
          placeholder="搜索技能名称 / 描述"
          defaultValue={initialQuery}
          onPressEnter={(e) => setKeyword((e.target as HTMLInputElement).value)}
          style={{ marginBottom: 20 }}
          allowClear
        />
        <div style={{ display: 'flex', gap: 20, alignItems: 'flex-start' }}>
          <Layout.Sider width={200} theme="light" style={{ background: '#fff', borderRadius: 8, padding: 8 }}>
            <Menu
              mode="inline"
              selectedKeys={category ? [category] : ['all']}
              onClick={(e) => setCategory(e.key === 'all' ? '' : e.key)}
              items={[
                { key: 'all', label: '全部分类' },
                ...categories.map(([cat, count]) => ({ key: cat, label: `${cat}（${count}）` })),
              ]}
            />
          </Layout.Sider>

          <div style={{ flex: 1 }}>
            {loading ? (
              <div style={{ textAlign: 'center', padding: 64 }}><Spin /></div>
            ) : items.length === 0 ? (
              <Empty description="暂无已发布技能" style={{ padding: 64 }} />
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 16 }}>
                {items.map((skill) => (
                  <Card key={skill.name} hoverable onClick={() => openDetail(skill.name)}>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Text strong>{skill.title || skill.name}</Text>
                      {skill.tier && <Tag color={TIER_COLORS[skill.tier]}>{skill.tier}</Tag>}
                    </div>
                    <Paragraph type="secondary" ellipsis={{ rows: 2 }} style={{ marginTop: 6 }}>
                      {skill.description || '（暂无描述）'}
                    </Paragraph>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Tag>{skill.category}</Tag>
                      <Text type="secondary">{skill.score != null ? `${skill.score.toFixed(1)} 分` : '评审中'}</Text>
                    </div>
                  </Card>
                ))}
              </div>
            )}
          </div>
        </div>

        {(detail || detailLoading) && (
          <div
            onClick={() => { setDetail(null); setDetailLoading(false) }}
            style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 1000,
                     display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}
          >
            <div onClick={(e) => e.stopPropagation()}
                 style={{ background: '#fff', borderRadius: 8, maxWidth: 720, width: '100%',
                          maxHeight: '80vh', overflow: 'auto', padding: 24 }}>
              {detailLoading || !detail ? <Spin /> : (
                <>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Typography.Title level={4} style={{ margin: 0 }}>{detail.title || detail.name}</Typography.Title>
                    {detail.tier && <Tag color={TIER_COLORS[detail.tier]}>Tier {detail.tier}</Tag>}
                  </div>
                  <Paragraph type="secondary" style={{ marginTop: 8 }}>{detail.description || '（暂无描述）'}</Paragraph>
                  <div style={{ marginBottom: 12, display: 'flex', gap: 8 }}>
                    <Tag>{detail.category}</Tag>
                    {(detail.industries ?? []).map((ind) => <Tag key={ind}>{ind}</Tag>)}
                    {detail.source_url && <a href={detail.source_url} target="_blank" rel="noreferrer">来源</a>}
                  </div>
                  {/* 不可信内容安全渲染：纯文本 <pre>（React 自动转义），不做 markdown/HTML 注入 */}
                  <pre data-testid="skill-md" style={{ background: '#fafafa', padding: 14, borderRadius: 6,
                       fontSize: 12, whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: 420, overflow: 'auto' }}>
                    {detail.skill_md || '（无正文）'}
                  </pre>
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default SkillsSquare
