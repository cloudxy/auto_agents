/**
 * 用量看板页（SaaS S3-2）：三指标 vs 配额进度条 + LLM 按供应商分摊。
 */
import React from 'react'
import { Alert, Card, Col, Progress, Row, Table, Typography } from 'antd'
import { useQuery } from '@tanstack/react-query'

import { QueryStateView } from '../components/QueryStateView'
import DeliveryWebhookCard from '../components/usage/DeliveryWebhookCard'
import BillingPanel from '../components/usage/BillingPanel'
import { fetchUsageByMember, fetchUsageOverview, type MemberUsageRow, type UsageOverview } from '../services/usage'
import { apiErrorMessage } from '../utils/errorMessage'

const { Title, Text } = Typography

const METRICS: Array<{ key: keyof UsageOverview['usage']; label: string; unit: string }> = [
  { key: 'task_concurrency', label: '任务并发', unit: '个运行中' },
  { key: 'result_storage', label: '结果存储', unit: '条结果' },
  { key: 'llm_tokens_month', label: 'LLM Token（本月）', unit: 'tokens' },
]

const Usage: React.FC = () => {
  const overviewQ = useQuery({
    queryKey: ['tenant-usage'],
    queryFn: fetchUsageOverview,
  })
  const memberQ = useQuery({
    queryKey: ['tenant-usage-members'],
    queryFn: fetchUsageByMember,
  })
  const data = overviewQ.data ?? null
  const loading = overviewQ.isLoading
  const error = overviewQ.isError ? apiErrorMessage(overviewQ.error, '用量加载失败') : null
  const byMember: MemberUsageRow[] = memberQ.data ?? []

  return (
    <QueryStateView loading={loading} error={error} data={data}>
      {(data) => (
    <div>
      <Alert type="info" showIcon style={{ marginBottom: 16 }}
             title="用量看板是租户维度；超配额的操作会被拒绝（429 QUOTA_EXCEEDED），文案含可行动建议" />
      <Row gutter={16}>
        {METRICS.map(({ key, label, unit }) => {
          const used = data.usage[key]
          const limit = data.quota[key]
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
      <Card title={`LLM 成本（本月 ${(data.cost_cents_total / 100).toFixed(2)} 元）`} style={{ marginTop: 16 }}>
        <Table
          rowKey="provider"
          size="small" pagination={false}
          dataSource={Object.entries(data.llm_by_provider).map(([provider, tokens]) => ({
            provider,
            tokens,
            cost: (data.cost_by_provider?.[provider] || 0) / 100,
          }))}
          columns={[
            { title: '供应商', dataIndex: 'provider', render: (v: string) => <Text code>{v}</Text> },
            { title: 'Tokens', dataIndex: 'tokens', render: (v: number) => v.toLocaleString() },
            { title: '金额（元）', dataIndex: 'cost', render: (v: number) => v.toFixed(2) },
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
              render: (v: string | null) => (v ? new Date(v).toLocaleString('zh-CN') : '-') },
          ]}
        />
      </Card>
      <DeliveryWebhookCard />
      <BillingPanel />
    </div>
      )}
    </QueryStateView>
  )
}

export default Usage
