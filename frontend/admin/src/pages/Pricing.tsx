/**
 * 后台定价（T-21）：专业/企业「去结账」；已登录不出现免费注册。
 * 买方进结账；经办/只读进屏 10。按钮字不随角色改口。禁 FR-U24 四字。
 */
import React, { useState } from 'react'
import { FREE_TIER_FEATURE_COPY, PRO_TIER_FEATURE_COPY } from '@auto-agents/frontend-shared'
import { Button, Card, Col, Row, Typography, message } from 'antd'
import { useNavigate } from 'react-router-dom'

import { ContactAdminModal } from '../components/quota/ContactAdminModal'
import {
  CHECKOUT_PATH_ENTERPRISE,
  CHECKOUT_PATH_PRO,
  PRICING_CTA_CHECKOUT,
} from '../constants/collectCopy'
import { useAuthStore } from '../store/useAuthStore'

const { Title, Text } = Typography

const TOUCH_TARGET_STYLE: React.CSSProperties = {
  minHeight: 'var(--size-touch, 44px)',
  minWidth: 'var(--size-touch, 44px)',
}

type PaidPlan = {
  name: string
  price: string
  features: string[]
  path: string
}

const PAID: PaidPlan[] = [
  {
    name: '专业档',
    price: '¥299/月',
    features: [
      PRO_TIER_FEATURE_COPY.task_concurrency,
      PRO_TIER_FEATURE_COPY.result_storage,
      PRO_TIER_FEATURE_COPY.llm_tokens_month,
      '工单支持',
    ],
    path: CHECKOUT_PATH_PRO,
  },
  {
    name: '企业档',
    price: '定制',
    features: [
      '不限并发（协商）',
      '专属存储配额',
      '专属 LLM 额度',
      '私有技能库',
      '中转站渠道组分配',
      '专属客户成功',
    ],
    path: CHECKOUT_PATH_ENTERPRISE,
  },
]

const Pricing: React.FC = () => {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const buyer = user?.tenant_role === 'owner' || user?.tenant_role === 'admin'
  const [contactOpen, setContactOpen] = useState(false)

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
      <Text type="secondary" style={{ display: 'block', marginBottom: 24 }}>三档价格如下。</Text>
      <Row gutter={24}>
        <Col xs={24} md={8}>
          <Card hoverable style={{ textAlign: 'center', height: '100%' }}>
            <Title level={4}>免费档</Title>
            <Title level={2} style={{ margin: '8px 0 20px' }}>¥0</Title>
            {[
              FREE_TIER_FEATURE_COPY.task_concurrency,
              FREE_TIER_FEATURE_COPY.result_storage,
              FREE_TIER_FEATURE_COPY.llm_tokens_month,
              '成员管理',
              '用量看板',
            ].map((text) => (
              <p key={text} style={{ textAlign: 'left', padding: '4px 0' }}>✓ {text}</p>
            ))}
          </Card>
        </Col>
        {PAID.map((plan) => (
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
                data-cta={plan.name === '专业档' ? 'pricing_pro' : 'pricing_enterprise'}
                onClick={() => onCheckout(plan.path)}
                className="site-touch-target"
                style={{ marginTop: 16, ...TOUCH_TARGET_STYLE }}
              >
                {PRICING_CTA_CHECKOUT}
              </Button>
            </Card>
          </Col>
        ))}
      </Row>
      <ContactAdminModal open={contactOpen} onClose={() => setContactOpen(false)} />
    </div>
  )
}

export default Pricing
