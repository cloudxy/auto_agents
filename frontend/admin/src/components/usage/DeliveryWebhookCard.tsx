/**
 * 租户交付 webhook：任务终态 HMAC POST（opt-in，空 URL 即关闭）。
 */
import React, { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Input, Space, Typography, message } from 'antd'
import { fetchDeliveryWebhook, putDeliveryWebhook } from '../../services/usage'
import { apiErrorMessage } from '../../utils/errorMessage'

const { Text } = Typography

const DeliveryWebhookCard: React.FC = () => {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['delivery-webhook'], queryFn: fetchDeliveryWebhook })
  const [url, setUrl] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (q.data) setUrl(q.data.delivery_webhook_url ?? '')
  }, [q.data])

  const onSave = async (next: string | null) => {
    try {
      setSaving(true)
      await putDeliveryWebhook(next)
      message.success(next ? '交付 webhook 已保存（任务终态将签名 POST）' : '已关闭交付 webhook')
      await qc.invalidateQueries({ queryKey: ['delivery-webhook'] })
    } catch (e) {
      message.error(apiErrorMessage(e, '保存失败'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card title="任务交付 Webhook" style={{ marginTop: 16 }} loading={q.isLoading}>
      {q.isError ? (
        <Alert type="error" showIcon style={{ marginBottom: 12 }}
               title={apiErrorMessage(q.error, 'Webhook 配置加载失败')} />
      ) : null}
      <Alert
        type="info" showIcon style={{ marginBottom: 12 }}
        title="默认关闭。填写 http(s) 地址后，任务完成/失败会带 HMAC 签名 POST 到该 URL（最多 3 次退避）。"
      />
      <Space.Compact style={{ width: '100%' }}>
        <Input
          placeholder="https://hooks.example.com/delivery"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          allowClear
        />
        <Button type="primary" loading={saving} onClick={() => onSave(url.trim() || null)}>保存</Button>
        <Button disabled={!url} loading={saving} onClick={() => { setUrl(''); void onSave(null) }}>关闭</Button>
      </Space.Compact>
      <Text type="secondary" style={{ display: 'block', marginTop: 8, fontSize: 12 }}>
        请求头含 x-webhook-timestamp / x-webhook-signature；密钥走 AUTO_AGENTS_WEBHOOK__SECRET_KEY。
      </Text>
    </Card>
  )
}

export default DeliveryWebhookCard
