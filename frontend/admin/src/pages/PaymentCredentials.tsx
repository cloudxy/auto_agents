/**
 * 支付渠道（超管专属，系统管理组叶）：支付宝/微信支付商户凭据配置。
 * 密钥只写不回读——GET 只见掩码；PUT 每次都要求重新粘贴完整密钥包（不支持
 * "只改商户号不改密钥"式增量更新，避免误判部分字段仍是旧值）。
 * 配置成功后，租户结账选该通道会自动拿到真实收银台链接/二维码（billing_service
 * .create_checkout → payment_provider.create_payment_intent）；未配置前该通道
 * 结账仍走线下挂账人工确认收款，不阻断下单。
 */
import React, { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, Button, Card, Descriptions, Form, Input, Modal, Space, Tag, Typography, message,
} from 'antd'
import { CheckCircleOutlined, ReloadOutlined } from '@ant-design/icons'

import { apiErrorMessage, isFormValidateError } from '../utils/errorMessage'
import {
  buildAlipaySecretsPayload, buildWechatSecretsPayload, deletePaymentCredential,
  fetchPaymentCredentials, putPaymentCredential, validatePaymentCredential,
  type PaymentChannel, type PaymentChannelCredentialView,
} from '../services/paymentCredentials'

const { Text, Paragraph } = Typography
const { TextArea } = Input

const LOAD_FAILED = '支付渠道配置加载失败。检查网络后重试。'
const CHANNEL_LABEL: Record<PaymentChannel, string> = { alipay: '支付宝', wechat: '微信支付' }
const NOTE = '未配置的通道，租户结账仍会正常下单，只是没有在线支付链接，需要超管人工确认收款。'
const SAVE_OK = '已保存商户凭据；密钥已加密落库，页面不会再回显明文。'
const DELETE_TITLE = '停用该支付通道？'
const DELETE_NOTE = '停用后租户结账选该通道会回退成人工确认收款，不影响已产生的订单。'

const formatTime = (v?: string | null) =>
  (v ? new Date(v).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '—')

type FormValues = {
  merchant_no: string
  // 支付宝
  app_id?: string
  app_private_key?: string
  alipay_public_key?: string
  // 微信支付
  api_v3_key?: string
  apiclient_key?: string
  cert_serial_no?: string
  appid?: string
}

const PaymentCredentials: React.FC = () => {
  const queryClient = useQueryClient()
  const listQuery = useQuery({ queryKey: ['payment-credentials'], queryFn: fetchPaymentCredentials })
  const channels = listQuery.data?.channels ?? []

  const [editing, setEditing] = useState<PaymentChannel | null>(null)
  const [editError, setEditError] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<PaymentChannel | null>(null)
  const [validateResult, setValidateResult] = useState<Record<string, string>>({})
  const [form] = Form.useForm<FormValues>()

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['payment-credentials'] })

  const saveMutation = useMutation({
    mutationFn: putPaymentCredential,
    onSuccess: () => {
      message.success(SAVE_OK)
      setEditing(null)
      setEditError(null)
      form.resetFields()
      invalidate()
    },
    onError: (e) => {
      if (isFormValidateError(e)) return
      setEditError(`保存失败：${apiErrorMessage(e, '请稍后重试')}`)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: deletePaymentCredential,
    onSuccess: (_, channel) => {
      message.success(`已停用${CHANNEL_LABEL[channel]}`)
      setDeleteTarget(null)
      invalidate()
    },
    onError: (e) => message.error(`停用失败：${apiErrorMessage(e, '请稍后重试')}`),
  })

  const validateMutation = useMutation({
    mutationFn: validatePaymentCredential,
    onSuccess: (r) => setValidateResult((s) => ({ ...s, [r.channel]: 'ok' })),
    onError: (e, channel) => setValidateResult((s) => ({
      ...s, [channel]: apiErrorMessage(e, '校验失败'),
    })),
  })

  const openEdit = (channel: PaymentChannel) => {
    setEditing(channel)
    setEditError(null)
    form.resetFields()
  }

  const onSave = async () => {
    if (!editing) return
    let values: FormValues
    try { values = await form.validateFields() } catch { return }
    const secrets = editing === 'alipay'
      ? buildAlipaySecretsPayload({
        app_id: values.app_id!.trim(),
        app_private_key: values.app_private_key!.trim(),
        alipay_public_key: values.alipay_public_key!.trim(),
      })
      : buildWechatSecretsPayload({
        mch_id: values.merchant_no.trim(),
        api_v3_key: values.api_v3_key!.trim(),
        apiclient_key: values.apiclient_key!.trim(),
        cert_serial_no: values.cert_serial_no!.trim(),
        appid: values.appid!.trim(),
      })
    saveMutation.mutate({ channel: editing, merchant_no: values.merchant_no.trim(), secrets })
  }

  if (listQuery.isError) {
    return (
      <Alert
        type="error" showIcon title={LOAD_FAILED}
        action={<Button size="small" onClick={() => listQuery.refetch()}>重试</Button>}
      />
    )
  }

  const rowOf = (channel: PaymentChannel): PaymentChannelCredentialView =>
    channels.find((c) => c.channel === channel) || { channel, configured: false }

  const renderCard = (channel: PaymentChannel) => {
    const row = rowOf(channel)
    const vr = validateResult[channel]
    return (
      <Card
        key={channel} title={CHANNEL_LABEL[channel]} size="small" style={{ marginBottom: 16 }}
        extra={row.configured
          ? <Tag icon={<CheckCircleOutlined />} color="green">已配置</Tag>
          : <Tag color="default">未配置</Tag>}
      >
        {row.configured ? (
          <Descriptions column={1} size="small" style={{ marginBottom: 12 }}>
            <Descriptions.Item label="商户号">{row.merchant_no || '—'}</Descriptions.Item>
            <Descriptions.Item label="密钥">
              <Text code>{row.secrets_masked || '********'}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="密钥版本">v{row.key_version ?? 1}</Descriptions.Item>
            <Descriptions.Item label="更新时间">{formatTime(row.updated_at)}</Descriptions.Item>
          </Descriptions>
        ) : (
          <Alert type="info" showIcon style={{ marginBottom: 12 }} title="尚未配置商户凭据" />
        )}
        <Space wrap>
          <Button type="primary" onClick={() => openEdit(channel)}>
            {row.configured ? '更新凭据' : '配置'}
          </Button>
          {row.configured ? (
            <>
              <Button
                loading={validateMutation.isPending && validateMutation.variables === channel}
                onClick={() => { setValidateResult((s) => ({ ...s, [channel]: '' })); validateMutation.mutate(channel) }}
              >
                校验格式
              </Button>
              <Button danger onClick={() => setDeleteTarget(channel)}>停用</Button>
            </>
          ) : null}
        </Space>
        {vr === 'ok' ? (
          <Alert type="success" showIcon style={{ marginTop: 12 }} title="密钥包格式与密钥可正常加载" />
        ) : vr ? (
          <Alert type="error" showIcon style={{ marginTop: 12 }} title={`校验未通过：${vr}`} />
        ) : null}
      </Card>
    )
  }

  return (
    <div>
      <Alert type="info" showIcon style={{ marginBottom: 12 }} title={NOTE} />
      <Space style={{ marginBottom: 12 }}>
        <Button icon={<ReloadOutlined />} loading={listQuery.isFetching} onClick={() => listQuery.refetch()}>刷新</Button>
      </Space>

      {renderCard('alipay')}
      {renderCard('wechat')}

      <Modal
        title={`配置${editing ? CHANNEL_LABEL[editing] : ''}商户凭据`} open={Boolean(editing)}
        okText="保存" confirmLoading={saveMutation.isPending} destroyOnHidden width={640}
        onOk={onSave} onCancel={() => setEditing(null)}
      >
        {editError && <Alert type="error" showIcon style={{ marginBottom: 12 }} title={editError} />}
        <Paragraph type="secondary">
          字段名与支付宝/微信支付开放平台商户后台一致，照抄申请页面原始内容粘贴即可；
          保存后密钥立即加密落库，本页不会再回显明文。
        </Paragraph>
        <Form form={form} layout="vertical">
          {editing === 'alipay' ? (
            <>
              <Form.Item
                name="merchant_no" label="支付宝商户号（PID，seller_id）"
                rules={[{ required: true, message: '请输入商户号' }]}
              >
                <Input placeholder="2088xxxxxxxxxxxx" />
              </Form.Item>
              <Form.Item
                name="app_id" label="应用 APPID" rules={[{ required: true, message: '请输入 APPID' }]}
              >
                <Input placeholder="2021xxxxxxxxxxxx" />
              </Form.Item>
              <Form.Item
                name="app_private_key" label="应用私钥（PEM 或密钥生成工具输出的纯 base64）"
                rules={[{ required: true, message: '请粘贴应用私钥' }]}
              >
                <TextArea rows={4} placeholder="-----BEGIN PRIVATE KEY-----&#10;...&#10;-----END PRIVATE KEY-----" />
              </Form.Item>
              <Form.Item
                name="alipay_public_key" label="支付宝公钥（公钥模式，非证书模式）"
                rules={[{ required: true, message: '请粘贴支付宝公钥' }]}
              >
                <TextArea rows={4} placeholder="-----BEGIN PUBLIC KEY-----&#10;...&#10;-----END PUBLIC KEY-----" />
              </Form.Item>
            </>
          ) : editing === 'wechat' ? (
            <>
              <Form.Item
                name="merchant_no" label="微信支付商户号（mch_id）"
                rules={[{ required: true, message: '请输入商户号' }]}
              >
                <Input placeholder="1900000109" />
              </Form.Item>
              <Form.Item name="appid" label="应用 APPID" rules={[{ required: true, message: '请输入 APPID' }]}>
                <Input placeholder="wxd678efh567hg6787" />
              </Form.Item>
              <Form.Item
                name="cert_serial_no" label="商户 API 证书序列号"
                rules={[{ required: true, message: '请输入证书序列号' }]}
              >
                <Input placeholder="444F4864EA9B34415..." />
              </Form.Item>
              <Form.Item
                name="apiclient_key" label="商户 API 证书私钥（apiclient_key.pem 内容）"
                rules={[{ required: true, message: '请粘贴证书私钥' }]}
              >
                <TextArea rows={4} placeholder="-----BEGIN PRIVATE KEY-----&#10;...&#10;-----END PRIVATE KEY-----" />
              </Form.Item>
              <Form.Item
                name="api_v3_key" label="APIv3 密钥"
                rules={[{ required: true, message: '请输入 APIv3 密钥' }]}
              >
                <Input.Password placeholder="商户平台「API安全」页设置的 32 位密钥" />
              </Form.Item>
            </>
          ) : null}
        </Form>
      </Modal>

      <Modal
        title={DELETE_TITLE} open={Boolean(deleteTarget)} okText="确认停用" okButtonProps={{ danger: true }}
        confirmLoading={deleteMutation.isPending} destroyOnHidden
        onOk={() => deleteTarget && deleteMutation.mutate(deleteTarget)}
        onCancel={() => setDeleteTarget(null)}
      >
        <Paragraph>{DELETE_NOTE}</Paragraph>
      </Modal>
    </div>
  )
}

export default PaymentCredentials
