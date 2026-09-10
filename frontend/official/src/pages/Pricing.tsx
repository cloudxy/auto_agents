/**
 * 定价页：闭集 A 免费档可买；闭集 B 与付费档标预告，主按钮不到 /register。
 */
import React, { useState } from 'react'
import { FREE_TIER_FEATURE_COPY } from '@auto-agents/frontend-shared'
import { Button, Card, Col, Modal, Row, Tag, Typography, message } from 'antd'
import { trackCta } from '../services/beacon'

const { Title, Text } = Typography

const CONTACT_MAIL = process.env.REACT_APP_CONTACT_MAIL || 'contact@localhost'
const TOUCH_TARGET_STYLE: React.CSSProperties = {
  minHeight: 'var(--size-touch, 44px)',
  minWidth: 'var(--size-touch, 44px)',
}

type FeatureItem = { text: string; preview?: boolean }

type Plan = {
  name: string
  price: string
  highlight: boolean
  comingSoon: boolean
  features: FeatureItem[]
  cta: { label: string; href?: string }
}

const PLANS: Plan[] = [
  {
    name: '免费档',
    price: '¥0',
    highlight: false,
    comingSoon: false,
    features: [
      { text: FREE_TIER_FEATURE_COPY.task_concurrency },
      { text: FREE_TIER_FEATURE_COPY.result_storage },
      { text: FREE_TIER_FEATURE_COPY.llm_tokens_month },
      { text: '成员管理' },
      { text: '用量看板' },
    ],
    cta: { label: '免费注册', href: '/register' },
  },
  {
    name: '专业档',
    price: '¥299/月',
    highlight: true,
    comingSoon: true,
    features: [
      { text: '50 个并发任务', preview: true },
      { text: '200,000 条结果存储', preview: true },
      { text: '500 万 LLM tokens/月', preview: true },
      { text: '工单支持', preview: true },
    ],
    cta: { label: '预告不可购买' },
  },
  {
    name: '企业档',
    price: '定制',
    highlight: false,
    comingSoon: true,
    features: [
      { text: '不限并发（协商）', preview: true },
      { text: '专属存储配额', preview: true },
      { text: '专属 LLM 额度', preview: true },
      { text: '私有技能库', preview: true },
      { text: '中转站渠道组分配', preview: true },
      { text: '专属客户成功', preview: true },
    ],
    cta: { label: '预告不可购买' },
  },
]

const Pricing: React.FC = () => {
  const [previewPlan, setPreviewPlan] = useState<string | null>(null)
  const [mailHint, setMailHint] = useState(false)

  const warnOfflineRegister = (event: React.MouseEvent) => {
    if (typeof navigator !== 'undefined' && !navigator.onLine) {
      event.preventDefault()
      message.warning('网络不可用。连接恢复后再创建企业。')
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--color-surface-sunken)' }}>
      <div style={{ maxWidth: 1080, margin: '0 auto', padding: '48px 24px 64px' }}>
        <div style={{ textAlign: 'center', marginBottom: 40 }}>
          <Title level={2} style={{ marginBottom: 8 }}>选择适合你的套餐</Title>
          <Text type="secondary">免费档现在可开通。专业档与企业档尚未开通购买。</Text>
        </div>
        <Row gutter={24}>
          {PLANS.map((plan) => (
            <Col xs={24} md={8} key={plan.name}>
              <Card hoverable style={{ textAlign: 'center', height: '100%' }}>
                {plan.comingSoon && <Tag style={{ marginBottom: 8 }}>预告</Tag>}
                <Title level={4}>{plan.name}</Title>
                <Title level={2} style={{ margin: '8px 0 20px' }}>
                  {plan.price}
                  {plan.comingSoon && (
                    <span style={{ display: 'block', fontSize: 14, fontWeight: 400, marginTop: 8 }}>
                      尚未开通购买
                    </span>
                  )}
                </Title>
                {plan.features.map((f) => (
                  <p key={f.text} style={{ textAlign: 'left', padding: '4px 0' }}>
                    ✓ {f.text}
                    {f.preview && (
                      <>
                        {' '}
                        <Tag>预告</Tag>
                      </>
                    )}
                  </p>
                ))}
                {plan.cta.href ? (
                  <Button
                    type="primary"
                    block
                    href={plan.cta.href}
                    data-cta="register_free"
                    onClick={(event) => {
                      trackCta('register_free')
                      warnOfflineRegister(event)
                    }}
                    className="site-touch-target"
                    style={{ marginTop: 16, ...TOUCH_TARGET_STYLE }}
                  >
                    {plan.cta.label}
                  </Button>
                ) : (
                  <Button
                    block
                    className="site-touch-target"
                    style={{ marginTop: 16, ...TOUCH_TARGET_STYLE }}
                    data-cta={plan.name === '专业档' ? 'pricing_pro' : 'pricing_enterprise'}
                    onClick={() => {
                      trackCta(plan.name === '专业档' ? 'pricing_pro' : 'pricing_enterprise')
                      setMailHint(false)
                      setPreviewPlan(plan.name)
                    }}
                  >
                    {plan.cta.label}
                  </Button>
                )}
              </Card>
            </Col>
          ))}
        </Row>
      </div>

      <Modal
        title="预告不可购买"
        open={previewPlan != null}
        onCancel={() => setPreviewPlan(null)}
        destroyOnHidden
        footer={[
          <Button
            key="mail"
            href={`mailto:${CONTACT_MAIL}`}
            onClick={() => setMailHint(true)}
          >
            联系平台
          </Button>,
          <Button key="ok" type="primary" onClick={() => setPreviewPlan(null)}>
            知道了
          </Button>,
        ]}
      >
        <p>该档尚未开通购买。</p>
        <p>
          {mailHint
            ? `邮件客户端没有打开。复制 ${CONTACT_MAIL} 联系平台。`
            : `联系平台：${CONTACT_MAIL}`}
        </p>
      </Modal>
    </div>
  )
}

export default Pricing
