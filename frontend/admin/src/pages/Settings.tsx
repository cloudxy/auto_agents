/**
 * 系统设置页面 - 管理网站基础信息
 */
import React, { useCallback, useEffect, useState } from 'react'
import { Form, Input, Button, Card, message, Divider, Spin } from 'antd'
import api from '../services/api'

const Settings: React.FC = () => {
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [fetching, setFetching] = useState(true)

  const fetchConfigs = useCallback(async () => {
    try {
      // /configs/ 直接返回 {key: value} 字典（无 ApiResponse 包装）
      const res: any = await api.get('/configs/')
      form.setFieldsValue(res)
    } catch (error) {
      message.error('获取配置失败')
    } finally {
      setFetching(false)
    }
  }, [form])

  useEffect(() => {
    fetchConfigs()
  }, [fetchConfigs])

  const onFinish = async (values: any) => {
    setLoading(true)
    try {
      // 遍历所有字段进行更新
      const keys = Object.keys(values)
      await Promise.all(
        keys.map(key => 
          api.put(`/configs/${key}`, { value: values[key] })
        )
      )
      message.success('系统配置已成功保存')
      // 提示用户官网已同步
      message.info('官网内容已实时同步更新')
    } catch (error) {
      console.error('Save error:', error)
      message.error('保存失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }

  if (fetching) {
    return <div style={{ textAlign: 'center', padding: '50px' }}><Spin tip="加载配置中..." /></div>
  }

  return (
    <div style={{ maxWidth: '800px', margin: '0 auto' }}>
      <Card title="全局系统设置" extra={<span style={{ color: '#999', fontSize: '12px' }}>修改后立即生效</span>}>
        <Form 
          form={form} 
          layout="vertical" 
          onFinish={onFinish}
          initialValues={{ site_title: 'AutoAgents', site_description: '' }}
        >
          <Form.Item 
            name="site_title" 
            label="网站/平台名称" 
            rules={[{ required: true, message: '平台名称不能为空' }]}
            tooltip="这将作为官网首页的主标题和管理后台的 Logo"
          >
            <Input placeholder="例如：AutoAgents 智能采集云平台" />
          </Form.Item>
          
          <Form.Item 
            name="site_description" 
            label="平台简介/SEO 描述"
            tooltip="展示在官网 Hero Section 的副标题，有助于 SEO"
          >
            <Input.TextArea 
              rows={4} 
              placeholder="请描述该平台的主要功能和核心优势..." 
            />
          </Form.Item>

          <Divider />

          <Form.Item style={{ marginBottom: 0, textAlign: 'right' }}>
            <Button type="primary" htmlType="submit" loading={loading} size="large" style={{ padding: '0 40px' }}>
              保存并发布
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}

export default Settings
