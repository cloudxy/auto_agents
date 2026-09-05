/**
 * 系统设置页面 - 管理网站基础信息
 */
import React, { useCallback, useEffect, useState } from 'react'
import { Tag, Form, Input, Button, Card, message, Divider, Spin } from 'antd'
import { fetchSiteConfigs, fetchWebhookStatus, updateSiteConfig, type WebhookStatus } from '../services/settings'
import { fetchNotifyConfig, updateNotifyConfig, type NotifyChannelConfig } from '../services/users'
import { apiErrorMessage } from '../utils/errorMessage'

/** 表单值契约（与 initialValues 的字段一致） */
interface SiteConfigValues {
  site_title: string
  site_description?: string
}

const Settings: React.FC = () => {
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [fetching, setFetching] = useState(true)
  const [webhook, setWebhook] = useState<WebhookStatus | null>(null)
  const [notifyCfg, setNotifyCfg] = useState<NotifyChannelConfig | null>(null)
  const [notifySaving, setNotifySaving] = useState(false)
  const [notifyForm] = Form.useForm()

  useEffect(() => {
    fetchWebhookStatus().then(setWebhook).catch(() => setWebhook(null))
    fetchNotifyConfig().then((cfg) => { setNotifyCfg(cfg); notifyForm.setFieldsValue(cfg) })
      .catch(() => setNotifyCfg(null))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const fetchConfigs = useCallback(async () => {
    try {
      form.setFieldsValue(await fetchSiteConfigs())
    } catch (error) {
      message.error('获取配置失败')
    } finally {
      setFetching(false)
    }
  }, [form])

  useEffect(() => {
    fetchConfigs()
  }, [fetchConfigs])

  const onSaveNotify = async () => {
    try {
      const values = await notifyForm.validateFields()
      setNotifySaving(true)
      await updateNotifyConfig(values)
      message.success('通知渠道配置已保存（下次通知即生效）')
    } catch (e) {
      if ((e as { errorFields?: unknown })?.errorFields) return
      message.error(apiErrorMessage(e, '保存通知渠道配置失败'))
    } finally {
      setNotifySaving(false)
    }
  }

  const onFinish = async (values: SiteConfigValues) => {
    setLoading(true)
    try {
      // 遍历所有字段进行更新（entries 避免字符串索引触发 TS7053）
      await Promise.all(
        Object.entries(values).map(([key, value]) =>
          updateSiteConfig(key, value)
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

      <Card title="Webhook 与通知渠道" style={{ marginTop: 16 }}>
        {webhook === null ? <Spin /> : (
          <p style={{ margin: '6px 0' }}>
            签名密钥：<Tag color={webhook.secret_configured ? 'success' : 'error'}>
              {webhook.secret_configured ? '已配置' : '未配置（外部回调可被伪造）'}
            </Tag>
            {webhook.env_override_active && <Tag color="blue">env 覆盖生效</Tag>}
            <span style={{ color: 'rgba(0,0,0,0.45)', fontSize: 13, marginLeft: 8 }}>
              密钥仅经 config/&lt;env&gt;/.env 注入（AUTO_AGENTS_WEBHOOK__SECRET_KEY），刻意不入库
            </span>
          </p>
        )}
        {notifyCfg === null ? <Spin /> : (
          <Form form={notifyForm} layout="vertical" style={{ marginTop: 8 }}>
            <Form.Item
              name="webhook_url" label="通用 Webhook 地址"
              rules={[{ pattern: /^https?:\/\/.+/, message: '必须是 http(s) 地址' }]}
              extra="任务终态/告警的通用回调；留空回退 .env 默认"
            >
              <Input placeholder="https://hooks.example.com/xxx" allowClear />
            </Form.Item>
            <Form.Item
              name="dingtalk_url" label="钉钉机器人 Webhook"
              rules={[{ pattern: /^https?:\/\/.+/, message: '必须是 http(s) 地址' }]}
            >
              <Input placeholder="https://oapi.dingtalk.com/robot/send?access_token=…" allowClear />
            </Form.Item>
            <Form.Item
              name="wechat_work_url" label="企业微信群机器人 Webhook"
              rules={[{ pattern: /^https?:\/\/.+/, message: '必须是 http(s) 地址' }]}
            >
              <Input placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=…" allowClear />
            </Form.Item>
            <Button type="primary" loading={notifySaving} onClick={onSaveNotify}>保存渠道配置</Button>
          </Form>
        )}
      </Card>
    </div>
  )
}

export default Settings
