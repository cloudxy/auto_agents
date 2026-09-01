/**
 * 用量看板页（SaaS S3-2）：三指标 vs 配额进度条 + LLM 按供应商分摊。
 */
import React, { useCallback, useEffect, useState } from 'react'
import { Alert, Card, Col, Progress, Row, Spin, Table, Typography, message } from 'antd'

import api, { unwrap } from '../services/api'

const { Title, Text } = Typography

interface UsageOverview {
  tenant_id: number
  quota: { task_concurrency: number; result_storage: number; llm_tokens_month: number }
  usage: { task_concurrency: number; result_storage: number; llm_tokens_month: number }
  llm_by_provider: Record<string, number>
}

const METRICS: Array<{ key: keyof UsageOverview['usage']; label: string; unit: string }> = [
  { key: 'task_concurrency', label: '任务并发', unit: '个运行中' },
  { key: 'result_storage', label: '结果存储', unit: '条结果' },
  { key: 'llm_tokens_month', label: 'LLM Token（本月）', unit: 'tokens' },
]

const Usage: React.FC = () => {
  const [data, setData] = useState<UsageOverview | null>(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setData(await api.get('/tenants/me/usage').then((r) => unwrap<UsageOverview>(r)))
    } catch (e) {
      message.error(`用量加载失败: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setLoading(false)
    }
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
    </div>
  )
}

export default Usage
