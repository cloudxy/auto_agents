/**
 * 企业注册页（SaaS S5-1）：公司名 + 管理员邮箱/密码 → tenant + owner（免费档）。
 */
import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { Alert, Button, Card, Checkbox, Form, Input, Typography, message } from 'antd'
import { CheckCircleOutlined } from '@ant-design/icons'
import { tenantSignup } from '../services/signup'
import { apiErrorMessage } from '../utils/errorMessage'


const { Title, Text } = Typography

const ADMIN_URL = process.env.REACT_APP_ADMIN_URL || 'http://localhost:9112'

interface SignupResult {
  tenant: { slug: string; name: string }
  owner: { username: string }
}

const Register: React.FC = () => {
  const [form] = Form.useForm()
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState<SignupResult | null>(null)

  const onSubmit = async () => {
    const values = await form.validateFields()
    try {
      setSubmitting(true)
      const result = await tenantSignup(values)
      setDone(result)
      message.success('注册成功，即可登录开始第一次采集')
    } catch (e) {
      message.error(apiErrorMessage(e, '注册失败'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: '#f7f9fc', display: 'flex',
                 alignItems: 'center', justifyContent: 'center', padding: 24 }}>
      <Card style={{ width: 420 }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Link to='/' style={{ fontSize: 20, fontWeight: 700, color: '#12233f', textDecoration: 'none' }}>AutoAgents</Link>
          <Title level={4} style={{ margin: '12px 0 4px' }}>企业注册</Title>
          <Text type="secondary">免费档：5 并发 / 10000 条结果 / 20 万 tokens/月</Text>
        </div>
        {done ? (
          <Alert type="success" showIcon icon={<CheckCircleOutlined />}
                 message={`企业「${done.tenant.name}」注册成功`}
                 description={(
                   <div>
                     <p>管理员账号：<Text code>{done.owner.username}</Text></p>
                     <p>首次登录后请尽快修改密码。</p>
                     <Button type="primary" href={`${ADMIN_URL}/login`}>进入管理后台登录</Button>
                     {' '}<Button href="/">返回官网</Button>
                   </div>
                 )} />
        ) : (
          <Form form={form} layout="vertical" onFinish={onSubmit}>
            <Form.Item name="company" label="公司名称" rules={[{ required: true, min: 2 }]}>
              <Input placeholder="如：Acme Corp" />
            </Form.Item>
            <Form.Item name="admin_email" label="管理员邮箱" rules={[{ required: true, type: 'email' }]}>
              <Input placeholder="admin@company.com" />
            </Form.Item>
            <Form.Item name="admin_password" label="初始密码" rules={[{ required: true, min: 8 }]}>
              <Input.Password placeholder="至少 8 位" autoComplete="new-password" />
            </Form.Item>
            <Form.Item
              name="agree"
              valuePropName="checked"
              rules={[{ validator: (_, v) => (v ? Promise.resolve() : Promise.reject(new Error('请先阅读并同意服务条款与隐私政策'))) }]}
            >
              <Checkbox>
                我已阅读并同意 <a href="/terms" target="_blank" rel="noreferrer">服务条款</a>
                {' '}与{' '}
                <a href="/privacy" target="_blank" rel="noreferrer">隐私政策</a>
              </Checkbox>
            </Form.Item>
            <Button type="primary" htmlType="submit" block loading={submitting}>创建企业租户</Button>
          </Form>
        )}
      </Card>
    </div>
  )
}

export default Register
