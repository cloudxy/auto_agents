/**
 * 登录页面
 */
import React, { useState } from 'react'
import { Form, Input, Button, Card, message, Typography, Checkbox } from 'antd'
import { UserOutlined, LockOutlined } from '@ant-design/icons'
import { useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '../store/useAuthStore'
import { apiErrorMessage } from '../utils/errorMessage'

const { Title } = Typography

const Login: React.FC = () => {
  const [loading, setLoading] = useState(false)
  const login = useAuthStore((state) => state.login)
  const navigate = useNavigate()
  const location = useLocation()

  // 获取登录前的页面路径（react-router location.state 类型宽松，显式窄化）
  const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname || '/dashboard'

  const onFinish = async (values: { username: string; password: string; remember_me?: boolean }) => {
    setLoading(true)
    try {
      await login({
        username: values.username,
        password: values.password,
        rememberMe: values.remember_me
      })
      message.success('登录成功')
      navigate(from, { replace: true })
    } catch (error) {
      // 后端统一异常格式为 {success, code, message}
      message.error(apiErrorMessage(error, '登录失败，请检查用户名和密码'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ 
      height: '100vh', 
      display: 'flex', 
      justifyContent: 'center', 
      alignItems: 'center',
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
    }}>
      <Card style={{ width: 400, boxShadow: '0 4px 12px rgba(0,0,0,0.15)' }}>
        <div style={{ textAlign: 'center', marginBottom: 30 }}>
          <Title level={2} style={{ margin: 0 }}>AutoAgents</Title>
          <p style={{ color: '#999' }}>管理后台登录</p>
        </div>
        
        <Form
          name="login"
          onFinish={onFinish}
          size="large"
        >
          <Form.Item
            name="username"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input 
              prefix={<UserOutlined />} 
              placeholder="用户名" 
            />
          </Form.Item>

          <Form.Item
            name="password"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="密码"
            />
          </Form.Item>

          <Form.Item name="remember_me" valuePropName="checked">
            <Checkbox>记住我（7天）</Checkbox>
          </Form.Item>

          <Form.Item>
            <Button 
              type="primary" 
              htmlType="submit" 
              loading={loading}
              block
            >
              登录
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}

export default Login
