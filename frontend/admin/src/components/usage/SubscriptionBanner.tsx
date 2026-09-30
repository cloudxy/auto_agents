/**
 * 当前套餐与到期状态（决策 D22）：
 * - 正常：当前套餐 + 有效期至
 * - 到期前 7 天：提示续费（续费从原到期日顺延，不损失剩余天数）
 * - 宽限期：已到期、哪天转为免费档、数据全部保留
 * 读取失败时不渲染（不挡用量页主体）。
 */
import React from 'react'
import { Alert, Button, Typography } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { formatDate } from '@auto-agents/frontend-shared'
import { fetchSubscription } from '../../services/billing'

const { Text } = Typography
const RENEW_WINDOW_MS = 7 * 86400000
const RENEW_PATH = '/billing/checkout?product=plan_pro'

const SubscriptionBanner: React.FC<{ canRenew: boolean }> = ({ canRenew }) => {
  const navigate = useNavigate()
  const query = useQuery({ queryKey: ['billing-subscription'], queryFn: () => fetchSubscription() })
  const sub = query.data
  if (!sub) return null

  const name = sub.plan_name || '免费档'
  const end = sub.current_period_end
  const renew = canRenew && sub.plan_slug === 'pro'
    ? <Button size="small" type="primary" onClick={() => navigate(RENEW_PATH)}>去续费</Button>
    : undefined

  if (sub.in_grace && end) {
    return (
      <Alert
        type="error" showIcon style={{ marginBottom: 16 }}
        title={`${name}已到期（${formatDate(end)}），${formatDate(sub.grace_until ?? null)} 起转为免费档`}
        description="宽限期内一切照常；转为免费档后数据全部保留，续费后立即恢复。"
        action={renew}
      />
    )
  }
  if (end && new Date(end).getTime() - Date.now() <= RENEW_WINDOW_MS) {
    return (
      <Alert
        type="warning" showIcon style={{ marginBottom: 16 }}
        title={`${name}即将到期（${formatDate(end)}）`}
        description="续费从原到期日顺延，不损失剩余天数；到期后另有宽限期。"
        action={renew}
      />
    )
  }
  return (
    <Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>
      当前套餐：{name}{end ? ` · 有效期至 ${formatDate(end)}` : ''}
    </Text>
  )
}

export default SubscriptionBanner
