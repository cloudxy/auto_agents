/**
 * 系统设置页面 - 管理网站基础信息
 *
 * 三态加载（审计 BUG-37 / B5-3）：加载中 / 失败（失败句 + 重试，不渲染表单） / 成功（接口值回填）。
 * 原先站点配置拉取失败会露出硬编码默认值，再点保存就把真实配置覆盖掉；通知渠道拉取失败则一直转圈。
 * 表单拿到数据后才挂载（initialValues + key），不在挂载前 setFieldsValue（useForm not connected 告警）。
 *
 * 文案只承诺已实现的能力（审计 B5-2）：设置只落库，不同步官网、后台 Logo 与 SEO。
 */
import React, { useState } from 'react'
import { Tag, Form, Input, Button, Card, message, Divider, Spin, Typography } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { fetchSiteConfigs, fetchWebhookStatus, updateSiteConfig } from '../services/settings'
import { fetchNotifyConfig, updateNotifyConfig } from '../services/users'
import { apiErrorMessage } from '../utils/errorMessage'
import { useAuthStore } from '../store/useAuthStore'
import { LoadFailure } from '../components/LoadState'
import NotFound from './NotFound'

const { Text } = Typography

/** 表单值契约（与 initialValues 的字段一致） */
interface SiteConfigValues {
  site_title: string
  site_description?: string
}

const SITE_KEYS = ['site-configs'] as const
const NOTIFY_KEYS = ['notify-config'] as const
const WEBHOOK_KEYS = ['webhook-status'] as const

/** T-21 / FR-M33：系统设置写面 = 平台超管 only。租户直打 = 404 同形，不是说明态。 */

const Settings: React.FC = () => {
  const user = useAuthStore((s) => s.user)
  const canWriteSettings = user?.is_platform_admin === true
  const [saving, setSaving] = useState(false)
  const [notifySaving, setNotifySaving] = useState(false)
  const [notifyForm] = Form.useForm()

  const siteQuery = useQuery({ queryKey: SITE_KEYS, queryFn: fetchSiteConfigs, enabled: canWriteSettings })
  const notifyQuery = useQuery({ queryKey: NOTIFY_KEYS, queryFn: fetchNotifyConfig, enabled: canWriteSettings })
  const webhookQuery = useQuery({ queryKey: WEBHOOK_KEYS, queryFn: fetchWebhookStatus, enabled: canWriteSettings })

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
    setSaving(true)
    try {
      // 逐键写入（entries 避免字符串索引触发 TS7053）；写后重拉，页面显示以库为准
      await Promise.all(
        Object.entries(values).map(([key, value]) => updateSiteConfig(key, value ?? '')),
      )
      // FR-90 / GWT-90.1：诚实句——只声明保存，不声明官网同步
      message.success('系统配置已保存')
      siteQuery.refetch()
    } catch (error) {
      message.error(apiErrorMessage(error, '保存失败，请稍后重试'))
    } finally {
      setSaving(false)
    }
  }

  if (!canWriteSettings) return <NotFound />

  const site = siteQuery.data as Partial<Record<keyof SiteConfigValues, unknown>> | undefined
  const siteInitial: SiteConfigValues = {
    site_title: typeof site?.site_title === 'string' ? site.site_title : '',
    site_description: typeof site?.site_description === 'string' ? site.site_description : '',
  }

  return (
    <div style={{ maxWidth: '800px', margin: '0 auto' }}>
      {/* §0.10 / GWT-99.1：页名「系统设置」唯一标题在顶栏；表单分区直接开始 */}
      <div style={{ marginBottom: 12 }}>
        <Text type="secondary">仅保存配置，暂未同步到官网与后台</Text>
      </div>
      {siteQuery.isPending ? (
        <div style={{ textAlign: 'center', padding: '50px' }}><Spin /></div>
      ) : siteQuery.isError ? (
        <LoadFailure title="系统配置加载失败。检查网络后重试。" onRetry={() => siteQuery.refetch()} />
      ) : (
        <Form
          key={siteQuery.dataUpdatedAt}
          layout="vertical"
          onFinish={onFinish}
          initialValues={siteInitial}
        >
          <Form.Item
            name="site_title"
            label="网站/平台名称"
            rules={[{ required: true, whitespace: true, message: '平台名称不能为空' }]}
          >
            <Input placeholder="例如：AutoAgents 智能采集云平台" maxLength={100} />
          </Form.Item>

          <Form.Item name="site_description" label="平台简介">
            <Input.TextArea rows={4} placeholder="请描述该平台的主要功能和核心优势..." />
          </Form.Item>

          <Divider />

          <Form.Item style={{ marginBottom: 0, textAlign: 'right' }}>
            <Button type="primary" htmlType="submit" loading={saving} size="large" style={{ padding: '0 40px' }}>
              保存
            </Button>
          </Form.Item>
        </Form>
      )}

      {/* 区块标题（§0.10：不复述页名，允许保留）；marginTop 16 = content.block-gap */}
      <Card title="Webhook 与通知渠道" style={{ marginTop: 16 }}>
        {webhookQuery.isPending ? <Spin /> : webhookQuery.isError ? (
          <LoadFailure title="Webhook 状态加载失败。检查网络后重试。" onRetry={() => webhookQuery.refetch()} />
        ) : (
          <p style={{ margin: '6px 0' }}>
            签名密钥：<Tag color={webhookQuery.data.secret_configured ? 'success' : 'error'}>
              {webhookQuery.data.secret_configured ? '已配置' : '未配置（外部回调可被伪造）'}
            </Tag>
            {webhookQuery.data.env_override_active && <Tag color="blue">env 覆盖生效</Tag>}
            <Text type="secondary" style={{ fontSize: 13, marginLeft: 8 }}>
              密钥仅经 config/&lt;env&gt;/.env 注入（AUTO_AGENTS_WEBHOOK__SECRET_KEY），刻意不入库
            </Text>
          </p>
        )}
        {notifyQuery.isPending ? <Spin /> : notifyQuery.isError ? (
          <LoadFailure
            title="通知渠道配置加载失败。检查网络后重试。"
            onRetry={() => notifyQuery.refetch()}
            style={{ marginTop: 8 }}
          />
        ) : (
          <Form
            key={notifyQuery.dataUpdatedAt}
            form={notifyForm}
            layout="vertical"
            style={{ marginTop: 8 }}
            initialValues={notifyQuery.data}
          >
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
