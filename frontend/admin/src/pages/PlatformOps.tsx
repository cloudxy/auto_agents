/**
 * 平台运营台（SaaS S5-2）：租户列表 / 套餐配额编辑 / 到期管理（平台超管专属）。
 */
import React, { useCallback, useEffect, useState } from 'react'
import {
  Alert, Button, DatePicker, Form, InputNumber, Modal, Space, Table, Tag,
  Typography, message,
} from 'antd'
import { ReloadOutlined, SettingOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import dayjs, { Dayjs } from 'dayjs'

import api, { unwrap } from '../services/api'

const { Text } = Typography

interface TenantRow {
  id: number
  slug: string
  name: string
  status: string
  quota: { task_concurrency?: number; result_storage?: number; llm_tokens_month?: number } | null
  expires_at: string | null
  created_at?: string | null
}

const STATUS_COLORS: Record<string, string> = {
  active: 'success', expired: 'error', disabled: 'warning',
}

const PlatformOps: React.FC = () => {
  const [rows, setRows] = useState<TenantRow[]>([])
  const [loading, setLoading] = useState(false)
  const [editing, setEditing] = useState<TenantRow | null>(null)
  const [form] = Form.useForm()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setRows(await api.get('/admin/tenants').then((r) => unwrap<TenantRow[]>(r)))
    } catch (e) {
      message.error(`租户列表加载失败: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const onSave = async () => {
    if (!editing) return
    const values = await form.validateFields()
    const payload: Record<string, unknown> = {}
    const quota: Record<string, number> = {}
    if (values.task_concurrency != null) quota.task_concurrency = values.task_concurrency
    if (values.result_storage != null) quota.result_storage = values.result_storage
    if (values.llm_tokens_month != null) quota.llm_tokens_month = values.llm_tokens_month
    if (Object.keys(quota).length) payload.quota = quota
    if (values.expires_at) payload.expires_at = (values.expires_at as Dayjs).toISOString()
    try {
      await api.patch(`/admin/tenants/${editing.id}`, payload)
      message.success(`租户 ${editing.slug} 已更新`)
      setEditing(null)
      load()
    } catch (e) {
      message.error(`保存失败: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const onToggleStatus = async (row: TenantRow) => {
    try {
      await api.patch(`/admin/tenants/${row.id}`,
                      { status: row.status === 'active' ? 'disabled' : 'active' })
      message.success(`租户 ${row.slug} 已${row.status === 'active' ? '禁用' : '启用'}`)
      load()
    } catch (e) {
      message.error(`操作失败: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const columns: ColumnsType<TenantRow> = [
    { title: 'Slug', dataIndex: 'slug', render: (v: string) => <Text code>{v}</Text> },
    { title: '企业名称', dataIndex: 'name' },
    {
      title: '状态', dataIndex: 'status', width: 100,
      render: (v: string) => <Tag color={STATUS_COLORS[v] || 'default'}>{v}</Tag>,
    },
    {
      title: '配额（并发/存储/Tokens）', width: 220,
      render: (_: unknown, row: TenantRow) => (
        <Text>
          {row.quota?.task_concurrency ?? '-'} / {row.quota?.result_storage ?? '-'} / {row.quota?.llm_tokens_month ?? '-'}
        </Text>
      ),
    },
    {
      title: '到期时间', dataIndex: 'expires_at', width: 150,
      render: (v: string | null) => (v ? new Date(v).toLocaleDateString('zh-CN') : '不过期'),
    },
    {
      title: '操作', width: 100,
      render: (_: unknown, row: TenantRow) => (
        <Space size={0}>
          <Button size="small" danger={row.status === 'active'}
                  onClick={() => onToggleStatus(row)}>
            {row.status === 'active' ? '禁用' : '启用'}
          </Button>
          <Button size="small" icon={<SettingOutlined />}
                onClick={() => {
                  setEditing(row)
                  form.setFieldsValue({
                    task_concurrency: row.quota?.task_concurrency,
                    result_storage: row.quota?.result_storage,
                    llm_tokens_month: row.quota?.llm_tokens_month,
                    expires_at: row.expires_at ? dayjs(row.expires_at) : undefined,
                  })
                }}>编辑</Button>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Alert type="info" showIcon style={{ marginBottom: 12 }}
             message="平台运营台为平台超管专属；到期租户会被登录拒绝（可行动文案），此处可续期/调整套餐" />
      <Space style={{ marginBottom: 12 }}>
        <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
      </Space>
      <Table rowKey="id" size="middle" loading={loading} columns={columns} dataSource={rows} pagination={false} />

      <Modal title={`编辑租户：${editing?.slug ?? ''}`} open={!!editing} onOk={onSave}
             onCancel={() => setEditing(null)} okText="保存">
        <Form form={form} layout="vertical">
          <Form.Item name="task_concurrency" label="任务并发配额">
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="result_storage" label="结果存储配额">
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="llm_tokens_month" label="LLM 月度 Token 配额">
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="expires_at" label="到期时间（留空=不过期）">
            <DatePicker showTime style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default PlatformOps
