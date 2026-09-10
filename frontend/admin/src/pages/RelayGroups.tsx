/**
 * 租户渠道组：常见中转站形态（组 + RPM/TPM + 模型名单 + 令牌）。
 * 不能改平台渠道/全局熔断（那是 /newapi 超管页）。
 */
import React, { useCallback, useEffect, useState } from 'react'
import {
  Alert, Button, Form, Input, InputNumber, Modal, Select, Space, Table, Tag, Typography, message,
} from 'antd'
import { ReloadOutlined } from '@ant-design/icons'

import { usePermission } from '../hooks/usePermission'
import { apiErrorMessage } from '../utils/errorMessage'
import {
  createRelayGroup, issueRelayToken, listRelayGroups, listRelayTokens, patchRelayGroup,
  revokeRelayToken, type RelayGroupRow, type RelayTokenRow,
} from '../services/relay'

const { Text, Paragraph } = Typography

const RelayGroups: React.FC = () => {
  const { role, isAdmin } = usePermission()
  const canWrite = isAdmin || role === 'admin'
  const [groups, setGroups] = useState<RelayGroupRow[]>([])
  const [tokens, setTokens] = useState<RelayTokenRow[]>([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [tokenOpen, setTokenOpen] = useState(false)
  const [issued, setIssued] = useState<string | null>(null)
  const [form] = Form.useForm()
  const [tokenForm] = Form.useForm()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [g, t] = await Promise.all([listRelayGroups(), listRelayTokens()])
      setGroups(g)
      setTokens(t)
    } catch (e) {
      message.error(apiErrorMessage(e, '渠道组加载失败'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const onCreate = async () => {
    const values = await form.validateFields()
    const models = String(values.models || '')
      .split(/[,，\s]+/).map((s: string) => s.trim()).filter(Boolean)
    try {
      await createRelayGroup({
        name: values.name,
        rpm_limit: values.rpm_limit || 0,
        tpm_limit: values.tpm_limit || 0,
        models,
      })
      message.success('渠道组已创建')
      setOpen(false)
      form.resetFields()
      load()
    } catch (e) {
      message.error(apiErrorMessage(e, '创建失败'))
    }
  }

  const onIssue = async () => {
    const values = await tokenForm.validateFields()
    try {
      const row = await issueRelayToken({
        group_id: values.group_id,
        name: values.name,
        quota_tokens: values.quota_tokens ?? -1,
      })
      setIssued(row.plaintext_key || null)
      setTokenOpen(false)
      tokenForm.resetFields()
      load()
    } catch (e) {
      message.error(apiErrorMessage(e, '签发失败'))
    }
  }

  return (
    <div>
      <Alert
        type="info" showIcon style={{ marginBottom: 12 }}
        title="渠道组只作用于本企业的令牌和限额。平台渠道窗口与熔断由值班超管在「中转站管控」维护，这里改不了。"
      />
      <Space style={{ marginBottom: 12 }}>
        {canWrite ? <Button type="primary" onClick={() => setOpen(true)}>新建渠道组</Button> : null}
        {canWrite ? <Button onClick={() => setTokenOpen(true)}>签发令牌</Button> : null}
        <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
      </Space>
      <Table rowKey="id" size="middle" loading={loading} dataSource={groups}
             pagination={{ pageSize: 20 }}
             columns={[
               { title: '组名', dataIndex: 'name' },
               { title: 'RPM', dataIndex: 'rpm_limit', render: (v: number) => (v ? v : '不限') },
               { title: 'TPM', dataIndex: 'tpm_limit', render: (v: number) => (v ? v : '不限') },
               { title: '模型', dataIndex: 'models', render: (v: string[]) => (v?.length ? v.join(', ') : '未限制') },
               { title: '状态', dataIndex: 'status', render: (v: string) => <Tag>{v === 'enabled' ? '启用' : '停用'}</Tag> },
               ...(canWrite ? [{
                 title: '操作',
                 render: (_: unknown, r: RelayGroupRow) => (
                   <Button size="small" onClick={() => patchRelayGroup(r.id, {
                     status: r.status === 'enabled' ? 'disabled' : 'enabled',
                   }).then(load)}>
                     {r.status === 'enabled' ? '停用' : '启用'}
                   </Button>
                 ),
               }] : []),
             ]} />
      <Typography.Title level={5} style={{ marginTop: 24 }}>令牌</Typography.Title>
      <Table rowKey="id" size="middle" loading={loading} dataSource={tokens}
             pagination={{ pageSize: 20 }}
             columns={[
               { title: '名称', dataIndex: 'name' },
               { title: '前缀', dataIndex: 'key_prefix', render: (v: string) => <Text code>{v}…</Text> },
               { title: '额度', dataIndex: 'quota_tokens', render: (v: number) => (v < 0 ? '不限' : v) },
               { title: '已用', dataIndex: 'used_tokens' },
               { title: '状态', dataIndex: 'status' },
               ...(canWrite ? [{
                 title: '操作',
                 render: (_: unknown, r: RelayTokenRow) => (
                   r.status === 'revoked' ? null : (
                     <Button size="small" danger onClick={() => revokeRelayToken(r.id).then(load)}>吊销</Button>
                   )
                 ),
               }] : []),
             ]} />
      <Modal title="新建渠道组" open={open} onOk={onCreate} onCancel={() => setOpen(false)} destroyOnHidden>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="组名" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="rpm_limit" label="RPM（0=不限）"><InputNumber min={0} style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="tpm_limit" label="TPM（0=不限）"><InputNumber min={0} style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="models" label="模型名单（逗号分隔，空=不限制）"><Input placeholder="gpt-4o, deepseek-chat" /></Form.Item>
        </Form>
      </Modal>
      <Modal title="签发令牌" open={tokenOpen} onOk={onIssue} onCancel={() => setTokenOpen(false)} destroyOnHidden>
        <Form form={tokenForm} layout="vertical">
          <Form.Item name="group_id" label="渠道组" rules={[{ required: true }]}>
            <Select options={groups.map((g) => ({ value: g.id, label: g.name }))} />
          </Form.Item>
          <Form.Item name="name" label="备注名" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="quota_tokens" label="额度（-1=不限）" initialValue={-1}>
            <InputNumber style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
      <Modal title="请立即复制令牌" open={Boolean(issued)} onOk={() => setIssued(null)} onCancel={() => setIssued(null)}>
        <Paragraph>明文只显示这一次，关闭后无法再看。</Paragraph>
        <Text code copyable>{issued}</Text>
      </Modal>
    </div>
  )
}

export default RelayGroups
