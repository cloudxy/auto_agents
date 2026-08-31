/**
 * 技能中心页（方案 A · A-P1c-1）
 *
 * 列表（筛选/搜索/排序/分页 + 双评分列 + 状态/tier 徽章）
 * + 详情 Drawer（SKILL.md 只读 + meta 原文 + 评分历史）
 * + 人工矫正 Modal（走 PUT /skills/{name}/meta，操作人=当前登录用户）。
 */
import React, { useCallback, useEffect, useState } from 'react'
import {
  Alert, Button, Drawer, Form, Input, InputNumber, message, Modal, Select,
  Space, Table, Tag, Typography,
} from 'antd'
import { ReloadOutlined, SyncOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'

import {
  correctSkillMeta, getSkillDetail, listSkills, scanSkills,
  type CorrectionPayload, type ScanSummary, type SkillDetail, type SkillItem,
} from '../services/skills'

const { Text, Paragraph } = Typography

const STATUS_COLORS: Record<string, string> = {
  experimental: 'default', testing: 'processing', stable: 'success',
  recommended: 'gold', deprecated: 'warning', blacklist: 'error',
}
const SYNC_COLORS: Record<string, string> = {
  ok: 'success', hash_changed: 'warning', missing: 'error', parse_error: 'error',
}
const TIER_COLORS: Record<string, string> = { S: 'gold', A: 'green', B: 'blue', C: 'default' }
const RUBRIC_DIMS = ['completeness', 'doc_quality', 'maintenance', 'real_world_effect'] as const

const Skills: React.FC<{ canEdit?: boolean; canAdmin?: boolean }> = ({ canEdit = false, canAdmin = false }) => {
  const [items, setItems] = useState<SkillItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [filters, setFilters] = useState<{ q?: string; category?: string; status?: string; tier?: string; sort: string }>({ sort: 'updated_at' })
  const [page, setPage] = useState(1)
  const [detail, setDetail] = useState<SkillDetail | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [correctTarget, setCorrectTarget] = useState<SkillItem | null>(null)
  const [form] = Form.useForm()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await listSkills({ ...filters, page, page_size: 20 })
      setItems(data.items)
      setTotal(data.total)
    } catch (e) {
      message.error(`技能列表加载失败: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setLoading(false)
    }
  }, [filters, page])

  useEffect(() => { load() }, [load])

  const openDetail = async (name: string) => {
    try {
      setDetail(await getSkillDetail(name))
      setDetailOpen(true)
    } catch (e) {
      message.error(`详情加载失败: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const runScan = async () => {
    try {
      const summary: ScanSummary = await scanSkills()
      message.success(`扫描完成：${summary.succeeded}/${summary.total} 成功，缺失 ${summary.missing.length} 个`)
      load()
    } catch (e) {
      message.error(`扫描失败: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const submitCorrection = async () => {
    if (!correctTarget) return
    const values = await form.validateFields()
    const payload: CorrectionPayload = {}
    if (values.category) payload.category = values.category
    if (values.status) payload.status = values.status
    if (values.score != null) payload.score = values.score
    if (values.review_notes) payload.review_notes = values.review_notes
    const rubric: Record<string, number> = {}
    let hasRubric = false
    RUBRIC_DIMS.forEach((dim) => {
      if (values[dim] != null) { rubric[dim] = values[dim]; hasRubric = true }
    })
    if (hasRubric) payload.rubric_human = rubric
    try {
      const result = await correctSkillMeta(correctTarget.name, payload)
      message.success(result.written_back ? `矫正成功（tier=${result.tier ?? '未评'}），meta.yaml 已写回` : '矫正已落库，meta.yaml 写回失败（可用补导出恢复）')
      setCorrectTarget(null)
      load()
    } catch (e) {
      message.error(`矫正失败: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const columns: ColumnsType<SkillItem> = [
    { title: '技能', dataIndex: 'name', render: (_, r) => (
      <a onClick={() => openDetail(r.name)}>{r.title || r.name}</a>
    )},
    { title: '分类', dataIndex: 'category', width: 140 },
    { title: '状态', dataIndex: 'status', width: 110, render: (s: string) => (
      <Tag color={STATUS_COLORS[s] || 'default'}>{s}</Tag>
    )},
    { title: 'Tier', dataIndex: 'tier', width: 70, render: (t?: string | null) => t ? <Tag color={TIER_COLORS[t]}>{t}</Tag> : <Text type="secondary">未评</Text> },
    { title: '人工终评', dataIndex: 'score', width: 95, render: (v?: number | null) => v != null ? v.toFixed(1) : '—' },
    { title: 'AI 建议', dataIndex: 'ai_suggested_score', width: 95, render: (v?: number | null) => v != null ? v.toFixed(1) : '—' },
    { title: '同步', dataIndex: 'sync_state', width: 105, render: (s: string) => (
      <Tag color={SYNC_COLORS[s] || 'default'}>{s}</Tag>
    )},
    { title: '更新时间', dataIndex: 'updated_at', width: 170, render: (v?: string | null) => v ? new Date(v).toLocaleString('zh-CN') : '—' },
    ...(canEdit ? [{
      title: '操作', width: 90, render: (_: unknown, r: SkillItem) => (
        <Button size="small" onClick={() => { setCorrectTarget(r); form.resetFields() }}>矫正</Button>
      ),
    }] : []),
  ]

  return (
    <div>
      {!canEdit && (
        <Alert type="info" showIcon style={{ marginBottom: 12 }} message="当前角色只读（矫正需 operator 及以上）" />
      )}
      <Space style={{ marginBottom: 12 }} wrap>
        <Input.Search
          placeholder="搜索 name/标题/描述"
          allowClear
          style={{ width: 220 }}
          onSearch={(q) => { setPage(1); setFilters((f) => ({ ...f, q })) }}
        />
        <Select
          placeholder="状态" allowClear style={{ width: 130 }}
          options={['experimental', 'testing', 'stable', 'recommended', 'deprecated'].map((s) => ({ value: s, label: s }))}
          onChange={(status) => { setPage(1); setFilters((f) => ({ ...f, status })) }}
        />
        <Select
          placeholder="Tier" allowClear style={{ width: 90 }}
          options={['S', 'A', 'B', 'C'].map((t) => ({ value: t, label: t }))}
          onChange={(tier) => { setPage(1); setFilters((f) => ({ ...f, tier })) }}
        />
        <Select
          style={{ width: 130 }} value={filters.sort}
          options={[
            { value: 'updated_at', label: '按更新时间' }, { value: 'score', label: '按评分' },
            { value: 'tier', label: '按 Tier' }, { value: 'name', label: '按名称' },
          ]}
          onChange={(sort) => setFilters((f) => ({ ...f, sort }))}
        />
        <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
        {canAdmin && <Button type="primary" icon={<SyncOutlined />} onClick={runScan}>扫描入库</Button>}
      </Space>

      <Table
        rowKey="id" size="middle" loading={loading}
        columns={columns} dataSource={items}
        pagination={{ current: page, pageSize: 20, total, showTotal: (t) => `共 ${t} 个技能`, onChange: setPage }}
      />

      <Drawer
        title={detail ? `${detail.title || detail.name}` : ''} width={640} open={detailOpen}
        onClose={() => setDetailOpen(false)}
      >
        {detail && (
          <div>
            <Paragraph type="secondary">{detail.description || '（无描述）'}</Paragraph>
            <Paragraph>
              分类 <Text code>{detail.category}</Text> · 状态 <Text code>{detail.status}</Text> · 来源 <Text code>{detail.source_type}</Text>
              {detail.source_url && <> · <a href={detail.source_url} target="_blank" rel="noreferrer">来源地址</a></>}
            </Paragraph>
            <Typography.Title level={5}>SKILL.md</Typography.Title>
            <pre style={{ maxHeight: 260, overflow: 'auto', background: '#fafafa', padding: 12, fontSize: 12 }}>{detail.skill_md || '（无内容）'}</pre>
            <Typography.Title level={5}>评分历史</Typography.Title>
            {detail.reviews.length === 0 && <Text type="secondary">暂无评审记录</Text>}
            {detail.reviews.map((rv) => (
              <Paragraph key={rv.id}>
                <Tag color={rv.reviewer_type === 'human' ? 'green' : 'blue'}>{rv.reviewer_type}</Tag>
                <Text strong>{rv.reviewer}</Text> · {rv.score != null ? rv.score.toFixed(1) : '—'}
                {rv.rubric && <Text type="secondary"> ({Object.entries(rv.rubric).map(([k, v]) => `${k}:${v}`).join(' ')})</Text>}
                {rv.notes && <br />}
                {rv.notes && <Text type="secondary">{rv.notes}</Text>}
              </Paragraph>
            ))}
          </div>
        )}
      </Drawer>

      <Modal
        title={`人工矫正：${correctTarget?.name ?? ''}`} open={!!correctTarget}
        onOk={submitCorrection} onCancel={() => setCorrectTarget(null)} destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item name="category" label="分类" initialValue={correctTarget?.category}>
            <Input placeholder="如 dev-tools" />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select allowClear options={['experimental', 'testing', 'stable', 'recommended', 'deprecated'].map((s) => ({ value: s, label: s }))} />
          </Form.Item>
          <Form.Item name="score" label="人工综合分（1-10）">
            <InputNumber min={1} max={10} step={0.1} style={{ width: '100%' }} />
          </Form.Item>
          {RUBRIC_DIMS.map((dim) => (
            <Form.Item key={dim} name={dim} label={`四维 · ${dim}（1-10）`}>
              <InputNumber min={1} max={10} style={{ width: '100%' }} />
            </Form.Item>
          ))}
          <Form.Item name="review_notes" label="终评笔记">
            <Input.TextArea rows={2} placeholder="real_world_effect 依据等" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default Skills
