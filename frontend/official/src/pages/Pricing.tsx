/**
 * 定价页（SaaS S5-2）：三档示意套餐（免费/专业/企业）。
 */
import React from 'react'
import { Button, Card, Col, Row, Tag, Typography } from 'antd'
import { useNavigate } from 'react-router-dom'

const { Title, Text } = Typography

const PLANS = [
  {
    name: '免费档', price: '¥0', color: '#1677ff', highlight: false,
    features: ['5 个并发任务', '10,000 条结果存储', '20 万 LLM tokens/月',
               '平台公共 LLM 供应商（兜底）', '社区支持'],
    cta: { label: '免费注册', href: '/register' },
  },
  {
    name: '专业档', price: '¥299/月', color: '#722ed1', highlight: true,
    features: ['50 个并发任务', '200,000 条结果存储', '500 万 LLM tokens/月',
               '自有 LLM Key（BYOK）', '成员管理 + 用量看板', '工单支持'],
    cta: { label: '联系升级', href: '/register' },
  },
  {
    name: '企业档', price: '定制', color: '#13c2c2', highlight: false,
    features: ['不限并发（协商）', '专属存储配额', '专属 LLM 额度',
               '私有技能库（评估开通）', '中转站渠道组分配', '专属客户成功'],
    cta: { label: '联系销售', href: '/register' },
  },
]

const Pricing: React.FC = () => {
  const navigate = useNavigate()
  return (
  <div style={{ minHeight: '100vh', background: '#f7f9fc' }}>
    <div style={{ maxWidth: 1080, margin: '0 auto', padding: '48px 24px 64px' }}>
      <div style={{ textAlign: 'center', marginBottom: 40 }}>
        <Title level={2} style={{ marginBottom: 8 }}>选择适合你的套餐</Title>
        <Text type="secondary">从免费档开始，随时升级；配额可在租户管理台调整</Text>
      </div>
      <Row gutter={24}>
        {PLANS.map((plan) => (
          <Col xs={24} md={8} key={plan.name}>
            <Card hoverable style={{ textAlign: 'center', height: '100%',
                                     border: plan.highlight ? `2px solid ${plan.color}` : undefined }}>
              {plan.highlight && <Tag color={plan.color} style={{ marginBottom: 8 }}>推荐</Tag>}
              <Title level={4}>{plan.name}</Title>
              <Title level={2} style={{ color: plan.color, margin: '8px 0 20px' }}>{plan.price}</Title>
              {plan.features.map((f) => (
                <p key={f} style={{ textAlign: 'left', padding: '4px 0' }}>✓ {f}</p>
              ))}
              <Button type="primary" block onClick={() => navigate(plan.cta.href)}
                      style={{ marginTop: 16, background: plan.color }}>{plan.cta.label}</Button>
            </Card>
          </Col>
        ))}
      </Row>
    </div>
  </div>
  )
}

export default Pricing
