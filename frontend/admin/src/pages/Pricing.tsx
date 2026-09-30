/**
 * 后台定价（T-21）：专业/企业「去结账」；已登录不出现免费注册。
 * 买方进结账；经办/只读进屏 10。按钮字不随角色改口。禁 FR-U24 四字。
 * 价格单一来源（审计 F1-1）：金额读后端 /billing/plans（与官网定价页、结账页同源），
 * 原先写死「¥299/月」「定制」，与官网和实际结账金额对不上；读取失败时提示「以结账页为准」。
 */
import React, { useState } from 'react'
import { FREE_TIER_FEATURE_COPY, PRO_TIER_FEATURE_COPY, contactMailto, formatPlanPrice } from '@auto-agents/frontend-shared'
import { Badge, Button, Card, Col, Row, Skeleton, Typography, message } from 'antd'
import { CheckOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import { ContactAdminModal } from '../components/quota/ContactAdminModal'
import {
  CHECKOUT_PATH_ENTERPRISE,
  CHECKOUT_PATH_PRO,
  PRICING_CTA_CHECKOUT,
} from '../constants/collectCopy'
import { fetchPublicContact, listPlans, type PlanRow } from '../services/billing'
import { useAuthStore } from '../store/useAuthStore'

const { Title, Text } = Typography

const TOUCH_TARGET_STYLE: React.CSSProperties = {
  minHeight: 'var(--size-touch, 44px)',
  minWidth: 'var(--size-touch, 44px)',
}

type PlanCard = {
  slug: string
  name: string
  highlight: boolean
  /** 按需定制、走「联系我们」（决策 D17）；价目接口的 sales_led 优先，读取失败时用这里的默认 */
  salesLed?: boolean
  features: string[]
  /** 付费档结账路径；免费档没有 */
  path?: string
}

const PLANS: PlanCard[] = [
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
    path: CHECKOUT_PATH_PRO,
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
    path: CHECKOUT_PATH_ENTERPRISE,
  },
]

const PriceTag: React.FC<{ slug: string; loading: boolean; plans: PlanRow[] | undefined }> = ({ slug, loading, plans }) => {
  if (loading) return <Skeleton.Input active size="large" style={{ width: 140, margin: '8px 0 20px' }} />
  const plan = plans?.find((p) => p.slug === slug)
  if (plan?.sales_led) return <Title level={2} style={{ margin: '8px 0 20px' }}>按需定制</Title>
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
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const buyer = user?.tenant_role === 'owner' || user?.tenant_role === 'admin'
  const [contactOpen, setContactOpen] = useState(false)
  const plansQuery = useQuery({ queryKey: ['billing-plans'], queryFn: () => listPlans() })
  const contactQuery = useQuery({ queryKey: ['public-contact'], queryFn: () => fetchPublicContact() })
  const contact = contactQuery.data ?? null
  const isSalesLed = (plan: PlanCard): boolean =>
    plansQuery.data?.find((p) => p.slug === plan.slug)?.sales_led ?? Boolean(plan.salesLed)

  const onCheckout = (path: string) => {
    if (typeof navigator !== 'undefined' && navigator.onLine === false) {
      message.warning('网络不可用。连接恢复后再去结账。')
      return
    }
    if (buyer) {
      navigate(path)
      return
    }
    setContactOpen(true)
  }

  return (
    <div data-testid="admin-pricing">
      <Title level={3} style={{ marginTop: 0 }}>选择适合你的套餐</Title>
      <Text type="secondary" style={{ display: 'block', marginBottom: 24 }}>从免费档开始，业务增长后再升级。</Text>
      <Row gutter={[24, 24]}>
        {PLANS.map((plan) => {
          const card = (
            <Card
              hoverable
              style={{
                textAlign: 'center',
                height: '100%',
                borderRadius: 12,
                border: plan.highlight ? '2px solid var(--color-primary)' : undefined,
                boxShadow: plan.highlight ? '0 12px 32px rgba(22,119,255,0.14)' : undefined,
              }}
              styles={{ body: { padding: '28px 24px' } }}
            >
              <Title level={4} style={{ marginBottom: 0 }}>{plan.name}</Title>
              <PriceTag slug={plan.slug} loading={plansQuery.isPending} plans={plansQuery.data} />
              <div style={{ borderTop: '1px solid rgba(0,0,0,0.06)', paddingTop: 16 }}>
                {plan.features.map((text) => (
                  <p key={text} style={{ textAlign: 'left', margin: 0, padding: '7px 0', display: 'flex', gap: 10, alignItems: 'baseline' }}>
                    <CheckOutlined aria-hidden style={{ color: 'var(--color-primary)', fontSize: 13 }} />
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
                    data-cta="pricing_enterprise"
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
              ) : plan.path && (
                <Button
                  type={plan.highlight ? 'primary' : 'default'}
                  block
                  size="large"
                  data-cta={plan.slug === 'pro' ? 'pricing_pro' : 'pricing_enterprise'}
                  onClick={() => onCheckout(plan.path as string)}
                  className="site-touch-target"
                  style={{ marginTop: 24, ...TOUCH_TARGET_STYLE }}
                >
                  {PRICING_CTA_CHECKOUT}
                </Button>
              )}
            </Card>
          )
          return (
            <Col xs={24} md={8} key={plan.slug}>
              {plan.highlight ? <Badge.Ribbon text="推荐" rootClassName="pricing-ribbon">{card}</Badge.Ribbon> : card}
            </Col>
          )
        })}
      </Row>
      <ContactAdminModal open={contactOpen} onClose={() => setContactOpen(false)} />
    </div>
  )
}

export default Pricing
