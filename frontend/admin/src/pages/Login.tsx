/**
 * 登录页：成功后来源回跳；页脚回官网企业注册（GWT-04.3）。
 */
import React, { useEffect, useState } from 'react'
import { Form, Input, Button, message, Typography, Checkbox, Alert } from 'antd'
import { UserOutlined, LockOutlined, RocketOutlined, CheckCircleFilled } from '@ant-design/icons'
import { useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '../store/useAuthStore'
import { apiErrorMessage, isFormValidateError } from '../utils/errorMessage'

const { Title, Text } = Typography

const OFFICIAL_URL = (process.env.REACT_APP_OFFICIAL_URL || 'http://localhost:9113').replace(/\/$/, '')
const OFFICIAL_REGISTER_HREF = `${OFFICIAL_URL}/register`

const COPY_CREDENTIALS = '用户名或密码不正确。核对后再登录。'
const COPY_EXPIRED = '企业已到期或停用，请联系平台'
const COPY_NETWORK = '登录请求失败，检查网络后重试。'
const COPY_SESSION_EXPIRED = '登录已过期。重新登录后回到刚才的页面。'
const COPY_LOCKED = '尝试过多，请稍后再登录。'

type LoginFormValues = { username: string; password: string; remember_me?: boolean }

type ApiErrorLike = {
  code?: string
  message?: string
  response?: { status?: number; data?: { code?: string; message?: string } }
}

const isApiErrorLike = (e: unknown): e is ApiErrorLike =>
  typeof e === 'object' && e !== null

const apiErrorCode = (e: unknown): string | undefined => {
  if (!isApiErrorLike(e)) return undefined
  return e.response?.data?.code || e.code
}

const isNetworkError = (e: unknown): boolean => {
  if (typeof navigator !== 'undefined' && navigator.onLine === false) return true
  if (!isApiErrorLike(e)) return false
  return e.response == null && !('errorFields' in e)
}

/** 只接受站内相对 path，防开放重定向 */
export const safeInternalPath = (raw: string | null | undefined): string => {
  const value = (raw || '').trim()
  if (!value.startsWith('/') || value.startsWith('//') || value.includes('://')) {
    return '/dashboard'
  }
  if (value.includes('\\') || value === '/login') return '/dashboard'
  return value
}

const fromLocationState = (state: unknown): string | undefined => {
  if (!state || typeof state !== 'object') return undefined
  const from = (state as { from?: unknown }).from
  if (typeof from === 'string') return from
  if (from && typeof from === 'object' && 'pathname' in from) {
    const loc = from as { pathname?: unknown; search?: unknown }
    const pathname = typeof loc.pathname === 'string' ? loc.pathname : undefined
    if (!pathname) return undefined
    const search = typeof loc.search === 'string' ? loc.search : ''
    return `${pathname}${search}`
  }
  return undefined
}

const loginErrorCopy = (e: unknown): string => {
  if (isNetworkError(e)) return COPY_NETWORK
  const code = apiErrorCode(e)
  if (
    code === 'TENANT_EXPIRED' ||
    code === 'TENANT_DISABLED' ||
    code === 'AUTH_TENANT_EXPIRED'
  ) {
    return COPY_EXPIRED
  }
  if (code === 'RATE_LIMITED' || (isApiErrorLike(e) && e.response?.status === 429)) {
    return COPY_LOCKED
  }
  if (code === 'AUTH_FAILED' || (isApiErrorLike(e) && e.response?.status === 401)) {
    return COPY_CREDENTIALS
  }
  return apiErrorMessage(e, COPY_NETWORK)
}

const Login: React.FC = () => {
  const [form] = Form.useForm<LoginFormValues>()
  const [loading, setLoading] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const login = useAuthStore((state) => state.login)
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)
  const navigate = useNavigate()
  const location = useLocation()

  const queryFrom = new URLSearchParams(location.search).get('from')
  const stateFrom = fromLocationState(location.state)
  const from = safeInternalPath(queryFrom || stateFrom)
  const sessionExpired = Boolean(
    location.state &&
      typeof location.state === 'object' &&
      (location.state as { sessionExpired?: boolean }).sessionExpired,
  )

  useEffect(() => {
    if (isAuthenticated) {
      navigate(from, { replace: true })
    }
  }, [isAuthenticated, from, navigate])

  const onFinish = async (values: LoginFormValues) => {
    if (typeof navigator !== 'undefined' && !navigator.onLine) {
      setFormError(COPY_NETWORK)
      return
    }
    setLoading(true)
    setFormError(null)
    try {
      await login({
        username: values.username,
        password: values.password,
        rememberMe: values.remember_me,
      })
      message.success('登录成功')
      navigate(from, { replace: true })
    } catch (error) {
      if (isFormValidateError(error)) return
      setFormError(loginErrorCopy(error))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      {/* 批次 5：左侧品牌区（与官网同一深空底与渐变）；窄屏隐藏，只留表单 */}
      <aside className="login-hero" aria-hidden>
        <div className="admin-brand" style={{ padding: 0, height: 'auto' }}>
          <span className="brand-mark"><RocketOutlined /></span>
          AutoAgents
        </div>
        <div>
          <h1>
            粘贴链接即可出数
            <br />
            <span className="login-hero-accent">智能数据采集</span>
          </h1>
          <ul>
            <li><CheckCircleFilled style={{ color: '#5cdbd3' }} />粘贴链接、提交任务、查看结果</li>
            <li><CheckCircleFilled style={{ color: '#5cdbd3' }} />AI 规划与试采，从链接走到入库</li>
            <li><CheckCircleFilled style={{ color: '#5cdbd3' }} />分布式 Worker 协同，结构化结果可导出</li>
          </ul>
        </div>
        <div className="login-hero-foot">AutoAgents 管理后台</div>
      </aside>

      <main className="login-panel">
        <div className="login-form">
          <div className="login-mobile-brand">
            <span className="brand-mark" aria-hidden><RocketOutlined /></span>
            AutoAgents
          </div>
          <div style={{ marginBottom: 28 }}>
            <Title level={3} style={{ margin: 0, color: 'var(--color-text-primary, #141414)' }}>
              登录管理后台
            </Title>
            <Text type="secondary">使用企业账号登录</Text>
          </div>

          {formError ? (
            <Alert type="error" showIcon title={formError} style={{ marginBottom: 16 }} role="alert" />
          ) : sessionExpired ? (
            <Alert type="warning" showIcon title={COPY_SESSION_EXPIRED} style={{ marginBottom: 16 }} role="status" />
          ) : null}

          <Form
            form={form}
            name="login"
            onFinish={onFinish}
            size="large"
            layout="vertical"
            requiredMark={false}
          >
            <Form.Item
              name="username"
              label="用户名"
              rules={[{ required: true, message: '请输入用户名' }]}
            >
              <Input
                prefix={<UserOutlined />}
                placeholder="用户名"
                autoComplete="username"
              />
            </Form.Item>

            <Form.Item
              name="password"
              label="密码"
              rules={[{ required: true, message: '请输入密码' }]}
            >
              <Input.Password
                prefix={<LockOutlined />}
                placeholder="密码"
                autoComplete="current-password"
              />
            </Form.Item>

            {/* 审计 BUG-07：会话时长由令牌决定（refresh 方案待 D10），不承诺具体天数 */}
            <Form.Item name="remember_me" valuePropName="checked">
              <Checkbox>记住我</Checkbox>
            </Form.Item>

            <Form.Item style={{ marginBottom: 12 }}>
              <Button
                type="primary"
                htmlType="submit"
                loading={loading}
                block
                autoInsertSpace={false}
              >
                {loading ? '登录中…' : '登录'}
              </Button>
            </Form.Item>
          </Form>

          {formError === COPY_NETWORK ? (
            <Button
              type="link"
              autoInsertSpace={false}
              onClick={() => {
                setFormError(null)
                form.submit()
              }}
              style={{ paddingLeft: 0 }}
            >
              重试
            </Button>
          ) : null}

          <p style={{ textAlign: 'center', marginBottom: 0, color: 'var(--color-text-secondary, #595959)' }}>
            没有账号？
            <Typography.Link href={OFFICIAL_REGISTER_HREF}>企业注册</Typography.Link>
          </p>
        </div>
      </main>
    </div>
  )
}

export default Login
