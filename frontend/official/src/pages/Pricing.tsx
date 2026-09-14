/**
 * 定价页（T-21）：免费档仍注册；专业/企业主按钮「去结账」。
 * 无会话分支（GWT-01.3）：访客与登录态同一 CTA 字；角色闸在结账。禁 FR-U24 四字。
 */
import React from 'react'
import { FREE_TIER_FEATURE_COPY, PRO_TIER_FEATURE_COPY } from '@auto-agents/frontend-shared'
import { Button, Card, Col, Row, Typography, message } from 'antd'
import { trackCta } from '../services/beacon'

const { Title, Text } = Typography

const ADMIN_URL = (process.env.REACT_APP_ADMIN_URL || 'http://localhost:9112').replace(/\/$/, '')
const TOUCH_TARGET_STYLE: React.CSSProperties = {
  minHeight: 'var(--size-touch, 44px)',
  minWidth: 'var(--size-touch, 44px)',
}

const checkoutHref = (product: 'plan_pro' | 'plan_enterprise'): string =>
  `${ADMIN_URL}/billing/checkout?product=${product}`

type Plan = {
  name: string
  price: string
  highlight: boolean
  features: string[]
  cta: { label: string; href: string; beacon: 'register_free' | 'pricing_pro' | 'pricing_enterprise' }
}

const PLANS: Plan[] = [
  {
    name: '免费档',
    price: '¥0',
    highlight: false,
    features: [
      FREE_TIER_FEATURE_COPY.task_concurrency,
      FREE_TIER_FEATURE_COPY.result_storage,
      FREE_TIER_FEATURE_COPY.llm_tokens_month,
      '成员管理',
      '用量看板',
    ],
    cta: { label: '免费注册', href: '/register', beacon: 'register_free' },
  },
  {
    name: '专业档',
    price: '¥299/月',
    highlight: true,
    features: [
      PRO_TIER_FEATURE_COPY.task_concurrency,
      PRO_TIER_FEATURE_COPY.result_storage,
      PRO_TIER_FEATURE_COPY.llm_tokens_month,
      '工单支持',
    ],
    cta: { label: '去结账', href: checkoutHref('plan_pro'), beacon: 'pricing_pro' },
  },
  {
    name: '企业档',
    price: '定制',
    highlight: false,
    features: [
      '不限并发（协商）',
      '专属存储配额',
      '专属 LLM 额度',
      '私有技能库',
      '中转站渠道组分配',
      '专属客户成功',
    ],
    cta: { label: '去结账', href: checkoutHref('plan_enterprise'), beacon: 'pricing_enterprise' },
  },
]

const Pricing: React.FC = () => {
  const warnOffline = (event: React.MouseEvent, kind: 'register' | 'checkout') => {
    if (typeof navigator !== 'undefined' && !navigator.onLine) {
      event.preventDefault()
      message.warning(
        kind === 'register'
          ? '网络不可用。连接恢复后再创建企业。'
          : '网络不可用。连接恢复后再去结账。',
      )
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--color-surface-sunken)' }}>
      <div style={{ maxWidth: 1080, margin: '0 auto', padding: '48px 24px 64px' }}>
        <div style={{ textAlign: 'center', marginBottom: 40 }}>
          <Title level={2} style={{ marginBottom: 8 }}>选择适合你的套餐</Title>
          <Text type="secondary">三档价格如下。</Text>
        </div>
        <Row gutter={24}>
          {PLANS.map((plan) => (
            <Col xs={24} md={8} key={plan.name}>
              <Card hoverable style={{ textAlign: 'center', height: '100%' }}>
                <Title level={4}>{plan.name}</Title>
                <Title level={2} style={{ margin: '8px 0 20px' }}>{plan.price}</Title>
                {plan.features.map((text) => (
                  <p key={text} style={{ textAlign: 'left', padding: '4px 0' }}>✓ {text}</p>
                ))}
                <Button
                  type="primary"
                  block
                  href={plan.cta.href}
                  data-cta={plan.cta.beacon}
                  onClick={(event) => {
                    trackCta(plan.cta.beacon)
                    warnOffline(event, plan.cta.beacon === 'register_free' ? 'register' : 'checkout')
                  }}
                  className="site-touch-target"
                  style={{ marginTop: 16, ...TOUCH_TARGET_STYLE }}
                >
                  {plan.cta.label}
                </Button>
              </Card>
            </Col>
          ))}
        </Row>
      </div>
    </div>
  )
}

export default Pricing
