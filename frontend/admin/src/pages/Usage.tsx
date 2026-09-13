/**
 * 用量看板（T-04 / FR-U02）：将满≠已尽；申请提升分角色（upgrade-intent，不建单）。
 * 内部码 QUOTA_EXCEEDED / 裸 429 禁止渲染给租户。禁 FR-U24 四字。
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Col, Progress, Row, Spin, Table, Tabs, Typography } from 'antd'

import { usePermission } from '../hooks/usePermission'
import { fetchUsageByMember, fetchUsageOverview, type MemberUsageRow, type UsageOverview } from '../services/usage'
import { apiErrorMessage } from '../utils/errorMessage'
import { UpgradeIntentButton } from '../components/quota/UpgradeIntentButton'
import {
  GO_SUBMIT_COLLECT,
  NEAR_LIMIT_COPY,
  PLAN_FULL_COPY,
  STORAGE_CTA,
} from '../constants/collectCopy'
import MyOrders from './MyOrders'

const { Title, Text } = Typography

const GATEWAY_UNREACHABLE = '平台 LLM 网关不可达'

const METRICS: Array<{ key: keyof NonNullable<UsageOverview['usage']>; label: string; unit: string }> = [
  { key: 'task_concurrency', label: '任务并发', unit: '个运行中' },
  { key: 'result_storage', label: '结果存储', unit: '条结果' },
  { key: 'llm_tokens_month', label: 'LLM Token（本月）', unit: 'tokens' },
]

type ApiErr = { response?: { data?: { code?: string; message?: string } } }
type TabKey = 'usage' | 'orders'

function tenantVisibleLoadError(e: unknown): string {
  const code = (e as ApiErr)?.response?.data?.code || ''
  if (code === 'LLM_GATEWAY_UNREACHABLE') return GATEWAY_UNREACHABLE
  if (code === 'LLM_COST_FUSE') {
    const msg = (e as ApiErr)?.response?.data?.message || '平台 LLM 成本熔断，请稍后重试'
    return msg.includes(PLAN_FULL_COPY) ? '平台 LLM 成本熔断，请稍后重试' : msg
  }
  if (code === 'QUOTA_EXCEEDED') return PLAN_FULL_COPY
  const raw = apiErrorMessage(e, '用量加载失败')
  return raw.replace(/QUOTA_EXCEEDED/g, '').replace(/\b429\b/g, '').trim() || '用量加载失败'
}

const Usage: React.FC = () => {
  const { role, isAdmin } = usePermission()
  const readonly = role === 'viewer' || (!isAdmin && role !== 'operator' && role !== 'admin')

  const [data, setData] = useState<UsageOverview | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [byMember, setByMember] = useState<MemberUsageRow[]>([])
  const [activeTab, setActiveTab] = useState<TabKey>('usage')

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
  const taskFull = ratios.task >= 1
  const needApply = tokenFull || taskFull
  const nearLimit = [ratios.token, ratios.storage, ratios.task].some((r) => r >= 0.9 && r < 1)
  const anyFull = tokenFull || storageFull || taskFull
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
    <Tabs
      activeKey={activeTab}
      onChange={(key) => setActiveTab(key as TabKey)}
      items={[
        {
          key: 'usage',
          label: '用量',
          children: (
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
                       action={<Button size="small" href="/spiders/tasks">{GO_SUBMIT_COLLECT}</Button>} />
              )}
              {nearLimit && (
                <Alert type="warning" showIcon style={{ marginBottom: 16 }} title={NEAR_LIMIT_COPY} />
              )}
              {anyFull && (
                <Alert
                  type="error"
                  showIcon
                  style={{ marginBottom: 16 }}
                  title={PLAN_FULL_COPY}
                  description={
                    <span>
                      {storageFull && (
                        <Button size="small" href="/data" style={{ marginRight: 8 }}>{STORAGE_CTA}</Button>
                      )}
                      {needApply && <UpgradeIntentButton />}
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
            </div>
          ),
        },
        {
          key: 'orders',
          label: '我的订单',
          children: <MyOrders onGoUsage={() => setActiveTab('usage')} />,
        },
      ]}
    />
  )
}

export default Usage
