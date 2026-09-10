/**
 * 企业注册：开通成功主按钮去后台登录；失败留在表单（GWT-04.1–04.4）。
 */
import React, { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Alert, Button, Card, Form, Input, Space, Typography, message } from 'antd'
import { CheckCircleOutlined } from '@ant-design/icons'
import { FREE_TIER_FEATURE_COPY } from '@auto-agents/frontend-shared'
import { getAnonymousId } from '../services/beacon'
import { tenantSignup, type SignupPayload, type SignupResult } from '../services/signup'
import { apiErrorMessage, isFormValidateError } from '../utils/errorMessage'

const { Title, Text } = Typography

const ADMIN_URL = (process.env.REACT_APP_ADMIN_URL || 'http://localhost:9112').replace(/\/$/, '')
const ADMIN_LOGIN_HREF = `${ADMIN_URL}/login?from=${encodeURIComponent('/dashboard')}`

const SIGNUP_INCOMPLETE_CODE = 'SIGNUP_INCOMPLETE'
const COPY_INCOMPLETE_GENERIC = '注册未完成，请检查填写内容'
const COPY_OFFLINE = '创建企业失败：网络不可用。检查连接后重试。'
const COPY_CREATED_TOAST = '企业已创建'
const COPY_LOGIN_ADMIN = '登录管理后台'
const COPY_REGISTER_ANOTHER = '再注册一家'
const FREE_TIER_LINE = `免费档：${FREE_TIER_FEATURE_COPY.task_concurrency} / ${FREE_TIER_FEATURE_COPY.result_storage} / ${FREE_TIER_FEATURE_COPY.llm_tokens_month}`
const TOUCH_TARGET_STYLE: React.CSSProperties = {
  minHeight: 'var(--size-touch, 44px)',
  minWidth: 'var(--size-touch, 44px)',
}

type ApiErrorLike = {
  code?: string
  message?: string
  response?: {
    status?: number
    data?: { code?: string; message?: string; request_id?: string }
  }
}

const isApiErrorLike = (e: unknown): e is ApiErrorLike =>
  typeof e === 'object' && e !== null

const apiErrorCode = (e: unknown): string | undefined => {
  if (!isApiErrorLike(e)) return undefined
  return e.response?.data?.code || e.code
}

const apiTraceId = (e: unknown): string | undefined => {
  if (!isApiErrorLike(e)) return undefined
  const id = e.response?.data?.request_id
  return id ? String(id) : undefined
}

const isNetworkError = (e: unknown): boolean => {
  if (typeof navigator !== 'undefined' && navigator.onLine === false) return true
  if (!isApiErrorLike(e)) return false
  return e.response == null && !('errorFields' in e)
}

const displayName = (raw: string | undefined): string => (raw || '').trim()

const successCopy = (company: string, username: string): string =>
  `企业「${company}」已开通，负责人 ${username}。登录后开始采集。`

const incompleteWithReason = (reason: string, traceId?: string): string => {
  const base = `注册未完成：${reason}。改正后再次创建企业。`
  return traceId ? `${base}错误编号 ${traceId}` : base
}

const Register: React.FC = () => {
  const [form] = Form.useForm<SignupPayload>()
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState<SignupResult | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const loginBtnRef = useRef<HTMLAnchorElement | HTMLButtonElement | null>(null)

  useEffect(() => {
    if (done) loginBtnRef.current?.focus()
  }, [done])

  const resetForAnother = () => {
    setDone(null)
    setFormError(null)
    form.resetFields()
  }

  const onFinish = async (values: SignupPayload) => {
    if (typeof navigator !== 'undefined' && !navigator.onLine) {
      setFormError(COPY_OFFLINE)
      return
    }
    try {
      setSubmitting(true)
      setFormError(null)
      const anonymousId = getAnonymousId()
      const result = await tenantSignup(
        anonymousId ? { ...values, anonymous_id: anonymousId } : values,
      )
      const company = displayName(result.tenant?.name)
      const username = displayName(result.owner?.username)
      if (!company || !username) {
        setFormError(incompleteWithReason('开通结果缺少企业名或负责人'))
        return
      }
      setDone({
        tenant: { name: company, slug: result.tenant.slug },
        owner: { username },
      })
      message.success(COPY_CREATED_TOAST)
    } catch (e) {
      if (isFormValidateError(e)) return
      if (isNetworkError(e)) {
        setFormError(COPY_OFFLINE)
        return
      }
      if (apiErrorCode(e) === SIGNUP_INCOMPLETE_CODE) {
        setFormError(COPY_INCOMPLETE_GENERIC)
        return
      }
      const reason = apiErrorMessage(e, '请检查填写内容')
      setFormError(incompleteWithReason(reason, apiTraceId(e)))
    } finally {
      setSubmitting(false)
    }
  }

  const companyName = displayName(done?.tenant.name)
  const ownerName = displayName(done?.owner.username)

  return (
    <div
      style={{
        minHeight: '100vh',
        background: 'var(--color-surface-sunken)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 24,
      }}
    >
      <Card style={{ width: 420, background: 'var(--color-surface)' }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Link
            to="/"
            style={{
              fontSize: 20,
              fontWeight: 700,
              color: 'var(--color-text-primary)',
              textDecoration: 'none',
            }}
          >
            AutoAgents
          </Link>
          <Title level={4} style={{ margin: '12px 0 4px', color: 'var(--color-text-primary)' }}>
            企业注册
          </Title>
          <Text type="secondary">{FREE_TIER_LINE}</Text>
        </div>
        {done && companyName && ownerName ? (
          <div aria-live="polite">
            <Alert
              type="success"
              showIcon
              icon={<CheckCircleOutlined />}
              title={
                <Text ellipsis={{ tooltip: companyName }} style={{ maxWidth: 340 }}>
                  {successCopy(companyName, ownerName)}
                </Text>
              }
              description={(
                <Space wrap style={{ marginTop: 8 }}>
                  <Button
                    type="primary"
                    href={ADMIN_LOGIN_HREF}
                    ref={loginBtnRef as React.Ref<HTMLAnchorElement>}
                    autoInsertSpace={false}
                    className="site-touch-target"
                    style={TOUCH_TARGET_STYLE}
                  >
                    {COPY_LOGIN_ADMIN}
                  </Button>
                  <Button autoInsertSpace={false} onClick={resetForAnother}>
                    {COPY_REGISTER_ANOTHER}
                  </Button>
                </Space>
              )}
            />
          </div>
        ) : (
          <Form
            form={form}
            layout="vertical"
            onFinish={onFinish}
            onFinishFailed={({ errorFields }) => {
              const name = errorFields[0]?.name
              if (name) form.scrollToField(name)
            }}
          >
            {formError ? (
              <Alert
                type="error"
                showIcon
                title={formError}
                style={{ marginBottom: 16 }}
                role="alert"
              />
            ) : null}
            <Form.Item
              name="company"
              label="企业名"
              rules={[
                { required: true, message: '请填写企业名' },
                { min: 2, message: '企业名至少 2 个字符' },
              ]}
            >
              <Input placeholder="如：Acme Corp" maxLength={128} />
            </Form.Item>
            <Form.Item
              name="admin_email"
              label="管理员邮箱"
              rules={[{ required: true, type: 'email', message: '请填写管理员邮箱' }]}
            >
              <Input placeholder="admin@company.com" autoComplete="username" />
            </Form.Item>
            <Form.Item
              name="admin_password"
              label="密码"
              rules={[
                { required: true, message: '请填写密码' },
                { min: 8, message: '密码至少 8 位' },
              ]}
            >
              <Input.Password placeholder="至少 8 位" autoComplete="new-password" />
            </Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              block
              loading={submitting}
              disabled={submitting}
              autoInsertSpace={false}
              className="site-touch-target"
              style={TOUCH_TARGET_STYLE}
            >
              {submitting ? '创建中…' : '创建企业'}
            </Button>
          </Form>
        )}
      </Card>
    </div>
  )
}

export default Register
