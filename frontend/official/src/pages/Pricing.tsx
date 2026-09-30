/**
 * 定价页（T-21）：免费档仍注册；专业/企业主按钮「去结账」。
 * 无会话分支（GWT-01.3）：访客与登录态同一 CTA 字；角色闸在结账。禁 FR-U24 四字。
 * 价格单一来源（审计 F1-1）：金额读后端 /billing/plans，页面不再手抄；读取失败时提示「以结账页为准」。
 */
import React from 'react'
import { FREE_TIER_FEATURE_COPY, PRO_TIER_FEATURE_COPY, contactMailto, formatPlanPrice } from '@auto-agents/frontend-shared'
import { Badge, Button, Card, Col, Row, Skeleton, Typography, message } from 'antd'
import { CheckOutlined } from '@ant-design/icons'
import { trackCta } from '../services/beacon'
import { usePublicPlans } from '../hooks/usePublicPlans'
import { usePublicContact } from '../hooks/usePublicContact'

const { Title, Text } = Typography

const ADMIN_URL = (process.env.REACT_APP_ADMIN_URL || 'http://localhost:9112').replace(/\/$/, '')
const TOUCH_TARGET_STYLE: React.CSSProperties = {
  minHeight: 'var(--size-touch, 44px)',
  minWidth: 'var(--size-touch, 44px)',
}

const checkoutHref = (product: 'plan_pro' | 'plan_enterprise'): string =>
  `${ADMIN_URL}/billing/checkout?product=${product}`

type Plan = {
  /** 后端价目 slug（free / pro / enterprise） */
  slug: string
  name: string
  highlight: boolean
  /** 按需定制、走「联系我们」（决策 D17）；价目接口的 sales_led 优先，读取失败时用这里的默认 */
  salesLed?: boolean
  features: string[]
  cta: { label: string; href: string; beacon: 'register_free' | 'pricing_pro' | 'pricing_enterprise' }
}

const PLANS: Plan[] = [
  {
    slug: 'free',
    name: '免费档',
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
    slug: 'pro',
    name: '专业档',
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
    slug: 'enterprise',
    name: '企业档',
    highlight: false,
    salesLed: true,
    // 决策 D32：「私有技能库」尚无对企业开放的实现，先从权益里撤下
    features: [
      '不限并发（协商）',
      '专属存储配额',
      '专属 LLM 额度',
      '中转站渠道组分配',
      '专属客户成功',
    ],
    cta: { label: '去结账', href: checkoutHref('plan_enterprise'), beacon: 'pricing_enterprise' },
  },
]

const PriceTag: React.FC<{ slug: string; state: ReturnType<typeof usePublicPlans> }> = ({ slug, state }) => {
  if (state.loading) {
    return <Skeleton.Input active size="large" style={{ width: 140, margin: '8px 0 20px' }} />
  }
  const plan = state.plans.find((p) => p.slug === slug)
  if (plan?.sales_led) {
    return <Title level={2} style={{ margin: '8px 0 20px' }}>按需定制</Title>
  }
  if (!plan) {
    return (
      <Text type="secondary" style={{ display: 'block', margin: '18px 0 26px' }}>
        {slug === 'free' ? '¥0' : '价格以结账页为准'}
      </Text>
    )
  }
  return <Title level={2} style={{ margin: '8px 0 20px' }}>{formatPlanPrice(plan)}</Title>
}

const Pricing: React.FC = () => {
  const plansState = usePublicPlans()
  const contact = usePublicContact()
  const isSalesLed = (plan: Plan): boolean =>
    plansState.plans.find((p) => p.slug === plan.slug)?.sales_led ?? Boolean(plan.salesLed)
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
          <Text type="secondary" style={{ fontSize: 15 }}>从免费档开始，业务增长后再升级。</Text>
        </div>
        <Row gutter={[24, 24]} align="stretch">
          {PLANS.map((plan) => {
            const card = (
              <Card
                hoverable
                style={{
                  textAlign: 'center',
                  height: '100%',
                  borderRadius: 12,
                  // 推荐档：主色描边 + 投影（批次 5：highlight 字段原先定义了没用上）
                  border: plan.highlight ? '2px solid var(--site-primary, #1677ff)' : undefined,
                  boxShadow: plan.highlight ? '0 12px 32px rgba(22,119,255,0.16)' : undefined,
                }}
                styles={{ body: { padding: '32px 28px' } }}
              >
                <Title level={4} style={{ marginBottom: 0 }}>{plan.name}</Title>
                <PriceTag slug={plan.slug} state={plansState} />
                <div style={{ borderTop: '1px solid rgba(0,0,0,0.06)', paddingTop: 16 }}>
                  {plan.features.map((text) => (
                    <p key={text} style={{ textAlign: 'left', margin: 0, padding: '7px 0', display: 'flex', gap: 10, alignItems: 'baseline' }}>
                      <CheckOutlined aria-hidden style={{ color: 'var(--site-primary, #1677ff)', fontSize: 13 }} />
                      <span>{text}</span>
                    </p>
                  ))}
                </div>
                {isSalesLed(plan) ? (
                  // 决策 D17：企业档按需定制，走「联系我们」（D25：邮箱 + 响应时效）
                  <>
                    <Button
                      block
                      size="large"
                      href={contactMailto(contact, `${plan.name}咨询`) ?? undefined}
                      disabled={!contactMailto(contact)}
                      data-cta={plan.cta.beacon}
                      onClick={() => trackCta(plan.cta.beacon)}
                      className="site-touch-target"
                      style={{ marginTop: 24, ...TOUCH_TARGET_STYLE }}
                    >
                      联系我们
                    </Button>
                    <Text type="secondary" style={{ display: 'block', marginTop: 8, fontSize: 13 }}>
                      {contactMailto(contact)
                        ? `${contact?.contact_email || contact?.duty_contact}${contact?.contact_sla ? ` · ${contact.contact_sla}` : ''}`
                        : '联系方式即将公布'}
                    </Text>
                  </>
                ) : (
                  <Button
                    type={plan.highlight ? 'primary' : 'default'}
                    block
                    size="large"
                    href={plan.cta.href}
                    data-cta={plan.cta.beacon}
                    onClick={(event) => {
                      trackCta(plan.cta.beacon)
                      warnOffline(event, plan.cta.beacon === 'register_free' ? 'register' : 'checkout')
                    }}
                    className="site-touch-target"
                    style={{ marginTop: 24, ...TOUCH_TARGET_STYLE }}
                  >
                    {plan.cta.label}
                  </Button>
                )}
              </Card>
            )
            return (
              <Col xs={24} md={8} key={plan.name}>
                {plan.highlight ? <Badge.Ribbon text="推荐" rootClassName="pricing-ribbon">{card}</Badge.Ribbon> : card}
              </Col>
            )
          })}
        </Row>
      </div>
    </div>
  )
}

export default Pricing
