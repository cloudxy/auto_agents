/**
 * 用量看板（FR-12）：三指标 vs 配额；满额/将满用户可见句；满额 CTA 不到企业注册。
 * 内部码 QUOTA_EXCEEDED / 裸 429 禁止渲染给租户。
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Alert, Button, Card, Col, Modal, Progress, Row, Spin, Table, Typography } from 'antd'

import { usePermission } from '../hooks/usePermission'
import { useAuthStore } from '../store/useAuthStore'
import { fetchUsageByMember, fetchUsageOverview, type MemberUsageRow, type UsageOverview } from '../services/usage'
import { apiErrorMessage } from '../utils/errorMessage'

const { Title, Text, Paragraph } = Typography

const CONTACT_MAIL = process.env.REACT_APP_CONTACT_MAIL || 'contact@localhost'
const PLAN_FULL = '已达配额上限'
const PLAN_FULL_CTA = '申请提升配额'
const NEAR_LIMIT = '接近上限。超额操作会被拒绝。'
const STORAGE_CTA = '去结果库'
const GATEWAY_UNREACHABLE = '平台 LLM 网关不可达'

const METRICS: Array<{ key: keyof NonNullable<UsageOverview['usage']>; label: string; unit: string }> = [
  { key: 'task_concurrency', label: '任务并发', unit: '个运行中' },
  { key: 'result_storage', label: '结果存储', unit: '条结果' },
  { key: 'llm_tokens_month', label: 'LLM Token（本月）', unit: 'tokens' },
]

type ApiErr = { response?: { data?: { code?: string; message?: string } } }

function tenantVisibleLoadError(e: unknown): string {
  const code = (e as ApiErr)?.response?.data?.code || ''
  if (code === 'LLM_GATEWAY_UNREACHABLE') return GATEWAY_UNREACHABLE
  if (code === 'LLM_COST_FUSE') {
    const msg = (e as ApiErr)?.response?.data?.message || '平台 LLM 成本熔断，请稍后重试'
    return msg.includes(PLAN_FULL) ? '平台 LLM 成本熔断，请稍后重试' : msg
  }
  if (code === 'QUOTA_EXCEEDED') return PLAN_FULL
  const raw = apiErrorMessage(e, '用量加载失败')
  return raw.replace(/QUOTA_EXCEEDED/g, '').replace(/\b429\b/g, '').trim() || '用量加载失败'
}

const Usage: React.FC = () => {
  const { role, isAdmin } = usePermission()
  const tenantRole = useAuthStore((s) => s.user?.tenant_role)
  const readonly = role === 'viewer' || tenantRole === 'viewer' || (!isAdmin && role !== 'operator' && role !== 'admin')

  const [data, setData] = useState<UsageOverview | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [byMember, setByMember] = useState<MemberUsageRow[]>([])
  const [contactOpen, setContactOpen] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      setData(await fetchUsageOverview())
    } catch (e) {
      setData(null)
      setLoadError(tenantVisibleLoadError(e))
    } finally {
      setLoading(false)
    }
    try {
      setByMember(await fetchUsageByMember())
    } catch { /* 成员分摊非关键路径 */ }
  }, [])

  useEffect(() => { load() }, [load])

  const usage = data?.usage
  const quota = data?.quota

  const ratios = useMemo(() => {
    if (!usage || !quota) return { token: 0, storage: 0, task: 0 }
    const pct = (used: number, limit: number) => (limit > 0 ? used / limit : 0)
    return {
      token: pct(usage.llm_tokens_month, quota.llm_tokens_month),
      storage: pct(usage.result_storage, quota.result_storage),
      task: pct(usage.task_concurrency, quota.task_concurrency),
    }
  }, [usage, quota])

  const tokenFull = ratios.token >= 1
  const storageFull = ratios.storage >= 1
  const nearLimit = [ratios.token, ratios.storage, ratios.task].some((r) => r >= 0.9 && r < 1)
  const anyFull = tokenFull || storageFull || ratios.task >= 1
  const unused = usage
    ? usage.task_concurrency === 0 && usage.result_storage === 0 && usage.llm_tokens_month === 0
    : false

  if (loading && !data && !loadError) return <Spin />
  if (loadError) {
    return <Alert type="error" showIcon title={loadError} />
  }
  if (data?.scope === 'platform' || data?.message === '用量属于企业空间') {
    return <Alert type="info" showIcon title="用量属于企业空间" />
  }
  if (!data || !usage || !quota) return <Alert type="warning" title="暂无用量数据" />

  return (
    <div>
      <Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>
        本月按 Asia/Shanghai 日历{data.year_month ? `（${data.year_month}）` : ''}
      </Text>
      {readonly && (
        <Alert type="info" showIcon style={{ marginBottom: 16 }}
               title="只读可见进度，不能改套餐" />
      )}
      {unused && !anyFull && !nearLimit && (
        <Alert type="info" showIcon style={{ marginBottom: 16 }}
               title="还没有用量。完成第一次采集后这里会显示配额进度。"
               action={<Link to="/spiders/tasks">去采集</Link>} />
      )}
      {nearLimit && (
        <Alert type="warning" showIcon style={{ marginBottom: 16 }} title={NEAR_LIMIT} />
      )}
      {anyFull && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          title={PLAN_FULL}
          description={
            <span>
              {tokenFull && (
                <Button type="primary" size="small" style={{ marginRight: 8 }}
                        onClick={() => setContactOpen(true)}>
                  {PLAN_FULL_CTA}
                </Button>
              )}
              {storageFull && (
                <Button size="small" href="/data">{STORAGE_CTA}</Button>
              )}
            </span>
          }
        />
      )}
      <Row gutter={16}>
        {METRICS.map(({ key, label, unit }) => {
          const used = usage[key]
          const limit = quota[key]
          const percent = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0
          return (
            <Col span={8} key={key}>
              <Card>
                <Text type="secondary">{label}</Text>
                <div style={{ margin: '12px 0' }}>
                  <Title level={3} style={{ margin: 0 }}>{used.toLocaleString()}</Title>
                  <Text type="secondary">/ {limit.toLocaleString()} {unit}</Text>
                </div>
                <Progress percent={percent} status={percent >= 90 ? 'exception' : percent >= 70 ? 'active' : 'normal'} />
              </Card>
            </Col>
          )
        })}
      </Row>
      <Card title="LLM 用量分摊（本月，按供应商）" style={{ marginTop: 16 }}>
        <Table
          rowKey="provider"
          size="small" pagination={false}
          dataSource={Object.entries(data.llm_by_provider || {}).map(([provider, tokens]) => ({ provider, tokens }))}
          columns={[
            { title: '供应商', dataIndex: 'provider', render: (v: string) => <Text code>{v}</Text> },
            { title: 'Tokens', dataIndex: 'tokens', render: (v: number) => v.toLocaleString() },
          ]}
          locale={{ emptyText: '本月暂无 LLM 用量' }}
        />
      </Card>
      <Card title="成员用量分摊（任务创建数）" style={{ marginTop: 16 }}>
        <Table<MemberUsageRow>
          rowKey="member"
          size="small"
          pagination={false}
          dataSource={byMember}
          columns={[
            { title: '成员', dataIndex: 'member' },
            { title: '任务数', dataIndex: 'tasks', width: 120 },
            { title: '最近活跃', dataIndex: 'last_active_at', width: 200,
              render: (v: string | null) => (v ? new Date(v).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '-') },
          ]}
        />
      </Card>
      <Modal
        title={PLAN_FULL_CTA}
        open={contactOpen}
        onCancel={() => setContactOpen(false)}
        footer={[
          <Button key="ok" type="primary" onClick={() => setContactOpen(false)}>知道了</Button>,
        ]}
      >
        <Paragraph>本波不提供自助改套餐或支付。请通过联系说明申请提升配额。</Paragraph>
        <a href={`mailto:${CONTACT_MAIL}`}>联系说明（{CONTACT_MAIL}）</a>
      </Modal>
    </div>
  )
}

export default Usage
