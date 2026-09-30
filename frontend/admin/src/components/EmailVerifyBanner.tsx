/**
 * 待验证邮箱提示（决策 D21）：企业负责人验证注册邮箱前，整家企业不能用 AI 规划。
 * 负责人可重新发送（60 秒一次）；成员提示请负责人验证。
 */
import React, { useState } from 'react'
import { Alert, Button, message } from 'antd'
import { resendVerification } from '../services/auth'
import { apiErrorMessage } from '../utils/errorMessage'
import { useAuthStore } from '../store/useAuthStore'

const EmailVerifyBanner: React.FC = () => {
  const user = useAuthStore((s) => s.user)
  const [sending, setSending] = useState(false)
  if (!user?.email_verify_pending) return null
  const isOwner = user.tenant_role === 'owner'

  const onResend = async () => {
    setSending(true)
    try {
      await resendVerification()
      message.success('验证邮件已发送，请查收注册邮箱')
    } catch (e) {
      message.error(apiErrorMessage(e, '发送失败，请稍后再试'))
    } finally {
      setSending(false)
    }
  }

  return (
    <Alert
      type="warning" showIcon style={{ marginBottom: 16 }}
      title={isOwner ? '验证注册邮箱后才能使用 AI 规划' : '企业负责人验证注册邮箱后才能使用 AI 规划'}
      description={isOwner ? '请到注册邮箱点击验证链接（72 小时内有效）。没收到可以重新发送。' : '请联系企业负责人完成邮箱验证。'}
      action={isOwner ? <Button size="small" loading={sending} onClick={onResend}>重新发送</Button> : undefined}
    />
  )
}

export default EmailVerifyBanner
