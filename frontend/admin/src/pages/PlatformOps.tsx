/**
 * 平台运营台（SaaS S5-2）：租户列表 / 套餐配额编辑 / 到期管理（平台超管专属）。
 */
import React, { useCallback, useEffect, useState } from 'react'
import {
  Alert, Button, DatePicker, Form, InputNumber, Modal, Popconfirm, Space, Table, Tag,
  Typography, message,
} from 'antd'
import { ReloadOutlined, SettingOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import dayjs, { Dayjs } from 'dayjs'
import { Tabs } from 'antd'
import { listTenants, patchTenant, type TenantRow } from '../services/platformOps'
import { clearDeadItems, discardDeadItem, listDeadItems, type DeadItem } from '../services/deadItems'
import { apiErrorMessage } from '../utils/errorMessage'


const { Text } = Typography

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
      setRows(await listTenants())
    } catch (e) {
      message.error(apiErrorMessage(e, '租户列表加载失败'))
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
      await patchTenant(editing.id, payload)
      message.success(`租户 ${editing.slug} 已更新`)
      setEditing(null)
      load()
    } catch (e) {
      message.error(apiErrorMessage(e, '保存失败'))
    }
  }

  const onToggleStatus = async (row: TenantRow) => {
    try {
      await patchTenant(row.id,
                      { status: row.status === 'active' ? 'disabled' : 'active' })
      message.success(`租户 ${row.slug} 已${row.status === 'active' ? '禁用' : '启用'}`)
      load()
    } catch (e) {
      message.error(apiErrorMessage(e, '操作失败'))
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


// ---------------- 死信队列 Tab（B6 工单 91：排障刚需） ----------------
const DeadItemsTab: React.FC = () => {
  const [items, setItems] = useState<DeadItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await listDeadItems()
      setItems(data.items)
      setTotal(data.total)
    } catch (e) {
      message.error(apiErrorMessage(e, '死信队列加载失败'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const onDiscard = async (index: number) => {
    try {
      await discardDeadItem(index)
      message.success('已丢弃')
      load()
    } catch (e) { message.error(apiErrorMessage(e, '丢弃失败')) }
  }

  const onClear = () => {
    Modal.confirm({
      title: `确认清空全部 ${total} 条死信？`,
      content: '死信是结果回流留档（缺 task_id 等无法归属的载荷），清空后不可恢复。',
      okText: '清空', okButtonProps: { danger: true }, cancelText: '取消',
      onOk: async () => {
        try {
          const r = await clearDeadItems()
          message.success(`已清除 ${r.removed} 条`)
          load()
        } catch (e) { message.error(apiErrorMessage(e, '清空失败')) }
      },
    })
  }

  return (
    <div>
      <Alert
        type="info" showIcon style={{ marginBottom: 12 }}
        message={`共 ${total} 条死信（最新在前）`}
        description="结果消息缺少 task_id 等无法归属时转入此队列留档；确认无用后可单条丢弃或清空。"
      />
      <Space style={{ marginBottom: 12 }}>
        <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
        <Button danger disabled={total === 0} onClick={onClear}>清空全部</Button>
      </Space>
      <Table
        rowKey="index" size="small" loading={loading} dataSource={items}
        pagination={{ pageSize: 20, showTotal: (t2) => `共 ${t2} 条` }}
        columns={[
          { title: '#', dataIndex: 'seq', width: 60 },
          { title: '采集方案', dataIndex: 'spider_name', width: 120, render: (v: string | null) => v || <Tag>未知</Tag> },
          { title: '载荷', dataIndex: 'raw', ellipsis: true, render: (v: string) => <Text code style={{ fontSize: 12 }}>{v}</Text> },
          { title: '解析', dataIndex: 'payload', width: 90, render: (v: DeadItem['payload']) => (v ? <Tag color="success">JSON</Tag> : <Tag color="error">损坏</Tag>) },
          { title: '操作', width: 90, render: (_: unknown, r: DeadItem) => (
            <Popconfirm title="确认丢弃该条死信？" okText="丢弃" okButtonProps={{ danger: true }} cancelText="取消"
                        onConfirm={() => onDiscard(r.index)}>
              <Button type="link" danger size="small">丢弃</Button>
            </Popconfirm>
          )},
        ]}
      />
    </div>
  )
}

  return (
    <div>
      <Tabs
        defaultActiveKey="tenants"
        items={[
          {
            key: 'tenants', label: '租户管理',
            children: (
              <>
      <Alert type="info" showIcon style={{ marginBottom: 12 }}
             message="平台运营台为平台超管专属；到期租户会被登录拒绝（可行动文案），此处可续期/调整套餐" />
      <Space style={{ marginBottom: 12 }}>
        <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
      </Space>
      <Table rowKey="id" size="middle" loading={loading} columns={columns} dataSource={rows} pagination={false} />

              </>
            ),
          },
          { key: 'dead-items', label: '死信队列', children: <DeadItemsTab /> },
        ]}
      />

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
