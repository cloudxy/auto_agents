/**
 * 用量看板页（SaaS S3-2）：三指标 vs 配额进度条 + LLM 按供应商分摊。
 */
import React, { useCallback, useEffect, useState } from 'react'
import { Alert, Card, Col, Progress, Row, Spin, Table, Typography, message } from 'antd'

import { fetchUsageByMember, fetchUsageOverview, type MemberUsageRow, type UsageOverview } from '../services/usage'
import { apiErrorMessage } from '../utils/errorMessage'

const { Title, Text } = Typography

const METRICS: Array<{ key: keyof UsageOverview['usage']; label: string; unit: string }> = [
  { key: 'task_concurrency', label: '任务并发', unit: '个运行中' },
  { key: 'result_storage', label: '结果存储', unit: '条结果' },
  { key: 'llm_tokens_month', label: 'LLM Token（本月）', unit: 'tokens' },
]

const Usage: React.FC = () => {
  const [data, setData] = useState<UsageOverview | null>(null)
  const [loading, setLoading] = useState(false)

  const [byMember, setByMember] = useState<MemberUsageRow[]>([])
  const load = useCallback(async () => {
    setLoading(true)
    try {
      setData(await fetchUsageOverview())
    } catch (e) {
      message.error(apiErrorMessage(e, '用量加载失败'))
    } finally {
      setLoading(false)
    }
    try {
      setByMember(await fetchUsageByMember())
    } catch { /* 成员分摊非关键路径 */ }
  }, [])

  useEffect(() => { load() }, [load])

  if (loading && !data) return <Spin />
  if (!data) return <Alert type="warning" message="暂无用量数据" />

  return (
    <div>
      <Alert type="info" showIcon style={{ marginBottom: 16 }}
             message="用量看板是租户维度；超配额的操作会被拒绝（429 QUOTA_EXCEEDED），文案含可行动建议" />
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
      <Card title="LLM 用量分摊（本月，按供应商）" style={{ marginTop: 16 }}>
        <Table
          rowKey="provider"
          size="small" pagination={false}
          dataSource={Object.entries(data.llm_by_provider).map(([provider, tokens]) => ({ provider, tokens }))}
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
              render: (v: string | null) => (v ? new Date(v).toLocaleString('zh-CN') : '-') },
          ]}
        />
      </Card>
    </div>
  )
}

export default Usage
