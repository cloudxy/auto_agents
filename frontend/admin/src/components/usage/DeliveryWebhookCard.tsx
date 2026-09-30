/**
 * 租户交付 webhook：任务终态 HMAC POST（opt-in，空 URL 即关闭）。
 *
 * 签名密钥按企业独立生成（审计 P0-8）：配置地址后展示本企业密钥，可复制、可轮换；
 * 只接受公网 http(s) 地址（内网 / 回环 / 元数据地址由后端拒绝）。
 */
import React, { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Input, Popconfirm, Space, Typography, message } from 'antd'
import { fetchDeliveryWebhook, putDeliveryWebhook } from '../../services/usage'
import { apiErrorMessage } from '../../utils/errorMessage'

const { Text, Paragraph } = Typography

const DeliveryWebhookCard: React.FC = () => {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['delivery-webhook'], queryFn: fetchDeliveryWebhook })
  const [url, setUrl] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (q.data) setUrl(q.data.delivery_webhook_url ?? '')
  }, [q.data])

  const save = async (next: string | null, rotate = false) => {
    try {
      setSaving(true)
      await putDeliveryWebhook(next, rotate)
      if (rotate) message.success('签名密钥已更换，请同步更新接收端的验签配置')
      else message.success(next ? '已保存，任务结束后会推送到这个地址' : '已关闭任务推送')
      await qc.invalidateQueries({ queryKey: ['delivery-webhook'] })
    } catch (e) {
      message.error(apiErrorMessage(e, '保存失败'))
    } finally {
      setSaving(false)
    }
  }

  const saved = q.data?.delivery_webhook_url ?? null
  const secret = q.data?.signing_secret ?? null

  return (
    <Card title="任务结果推送（Webhook）" style={{ marginTop: 16 }} loading={q.isLoading}>
      {q.isError ? (
        <Alert type="error" showIcon style={{ marginBottom: 12 }}
               title={apiErrorMessage(q.error, 'Webhook 配置加载失败')} />
      ) : null}
      <Paragraph type="secondary" style={{ marginBottom: 12 }}>
        默认关闭。填写公网 http(s) 地址后，任务完成或失败时会把结果摘要以带签名的 POST 推送到该地址，失败最多重试 3 次。
      </Paragraph>
      <Space.Compact style={{ width: '100%' }}>
        <Input
          aria-label="Webhook 地址"
          placeholder="https://hooks.example.com/delivery"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          allowClear
        />
        <Button type="primary" loading={saving} onClick={() => save(url.trim() || null)}>保存</Button>
        <Button disabled={!saved} loading={saving} onClick={() => { setUrl(''); void save(null) }}>关闭</Button>
      </Space.Compact>
      {saved && secret ? (
        <div style={{ marginTop: 16 }}>
          <Text strong>签名密钥</Text>
          <Space style={{ display: 'flex', marginTop: 6 }} wrap>
            <Text code copyable={{ text: secret, tooltips: ['复制', '已复制'] }}>
              {`${secret.slice(0, 10)}••••••••${secret.slice(-4)}`}
            </Text>
            <Popconfirm
              title="更换签名密钥？"
              description="更换后旧密钥立即失效，接收端需要同步更新。"
              okText="更换"
              cancelText="取消"
              onConfirm={() => save(saved, true)}
            >
              <Button size="small" loading={saving}>更换密钥</Button>
            </Popconfirm>
          </Space>
          <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0, fontSize: 12 }}>
            验签方法：用本密钥对「x-webhook-timestamp + &quot;.&quot; + 请求体原文」做 HMAC-SHA256，
            结果应与请求头 x-webhook-signature 一致；建议同时拒绝 5 分钟以前的时间戳。
          </Paragraph>
        </div>
      ) : null}
    </Card>
  )
}

export default DeliveryWebhookCard
