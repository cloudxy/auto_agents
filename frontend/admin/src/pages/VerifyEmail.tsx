/**
 * 邮箱验证落地页（决策 D21）：注册邮件里的链接指到这里，无需登录。
 * 验证成功后若已登录，就地清掉「待验证」标记（AI 规划入口随即可用）。
 */
import React, { useEffect, useState } from 'react'
import { Button, Result, Spin } from 'antd'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { verifyEmail } from '../services/auth'
import { apiErrorMessage } from '../utils/errorMessage'
import { useAuthStore } from '../store/useAuthStore'

type State = { kind: 'pending' } | { kind: 'ok' } | { kind: 'failed'; message: string }

const VerifyEmail: React.FC = () => {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const [state, setState] = useState<State>({ kind: 'pending' })
  const token = params.get('token') || ''

  useEffect(() => {
    let alive = true
    if (!token) {
      setState({ kind: 'failed', message: '验证链接不完整，请从邮件里重新打开，或在后台重新发送。' })
      return undefined
    }
    verifyEmail(token)
      .then(() => {
        if (!alive) return
        useAuthStore.setState((s) => (s.user ? { user: { ...s.user, email_verify_pending: false } } : {}))
        setState({ kind: 'ok' })
      })
      .catch((e) => { if (alive) setState({ kind: 'failed', message: apiErrorMessage(e, '验证链接无效或已过期，请在后台重新发送。') }) })
    return () => { alive = false }
  }, [token])

  const next = isAuthenticated ? '/ai' : '/login'
  if (state.kind === 'pending') {
    return <div style={{ padding: 80, textAlign: 'center' }}><Spin /></div>
  }
  return (
    <Result
      status={state.kind === 'ok' ? 'success' : 'warning'}
      title={state.kind === 'ok' ? '邮箱已验证' : '没能完成验证'}
      subTitle={state.kind === 'ok' ? '现在可以使用 AI 规划了。' : state.message}
      extra={<Button type="primary" onClick={() => navigate(next)}>{isAuthenticated ? '去 AI 规划' : '去登录'}</Button>}
    />
  )
}

export default VerifyEmail
