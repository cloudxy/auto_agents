/**
 * 平台运营台（SaaS S5-2）：租户列表 / 套餐配额编辑 / 到期管理（平台超管专属）。
 */
import React, { useCallback, useEffect, useRef, useState } from 'react'
import {
  Alert, Button, DatePicker, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Table, Tag,
  Typography, message,
} from 'antd'
import { ReloadOutlined, SettingOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import dayjs, { Dayjs } from 'dayjs'
import { Tabs } from 'antd'
import { listTenants, patchTenant, type TenantRow } from '../services/platformOps'
import { clearDeadItems, discardDeadItem, listDeadItems, type DeadItem } from '../services/deadItems'
import { apiErrorMessage } from '../utils/errorMessage'
import PendingOrdersTab from '../components/ops/PendingOrdersTab'
import { grantPlan } from '../services/billing'
import ProductEvents from './ProductEvents'
import { formatDate } from '@auto-agents/frontend-shared'


const { Text } = Typography

const STATUS_COLORS: Record<string, string> = {
  active: 'success', expired: 'error', disabled: 'warning',
}
const STATUS_LABELS: Record<string, string> = {
  active: '正常', expired: '已到期', disabled: '已禁用',
}
/** 平台租户（超管所在）与默认租户（个人注册账号所在）不可停用；后端同样拒绝（tenant_admin_service） */
const PROTECTED_SLUGS = new Set(['platform', 'default'])

const PlatformOps: React.FC = () => {
  const [rows, setRows] = useState<TenantRow[]>([])
  const [loading, setLoading] = useState(false)
  const [editing, setEditing] = useState<TenantRow | null>(null)
  const [form] = Form.useForm()
  // 审计 BUG-38：禁用整家企业 = 全员无法登录，必须二次确认、填原因（记入审计）、进行中锁
  const [disabling, setDisabling] = useState<TenantRow | null>(null)
  const [disableSubmitting, setDisableSubmitting] = useState(false)
  const disableInFlight = useRef(false)
  const [disableForm] = Form.useForm()
  // 决策 D17：企业档走销售，成交后在这里开通（记一笔线下已收款订单 + 同一履约路径）
  const [granting, setGranting] = useState<TenantRow | null>(null)
  const [grantSubmitting, setGrantSubmitting] = useState(false)
  const [grantForm] = Form.useForm()

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

  const onEnable = async (row: TenantRow) => {
    try {
      await patchTenant(row.id, { status: 'active' })
      message.success(`企业 ${row.name} 已启用`)
      load()
    } catch (e) {
      message.error(apiErrorMessage(e, '操作失败'))
    }
  }

  const onConfirmGrant = async () => {
    if (!granting || grantSubmitting) return
    let values: { product: 'plan_enterprise' | 'plan_pro'; amount_yuan: number; periods: number; note?: string }
    try {
      values = await grantForm.validateFields()
    } catch {
      return
    }
    setGrantSubmitting(true)
    try {
      await grantPlan(granting.id, {
        product: values.product,
        amount_cents: Math.round(Number(values.amount_yuan) * 100),
        periods: Number(values.periods),
        note: (values.note || '').trim(),
      })
      message.success(`已为 ${granting.name} 开通`)
      setGranting(null)
      load()
    } catch (e) {
      message.error(apiErrorMessage(e, '开通失败'))
    } finally {
      setGrantSubmitting(false)
    }
  }

  const onConfirmDisable = async () => {
    if (!disabling || disableInFlight.current) return
    let reason: string
    try {
      reason = String((await disableForm.validateFields()).reason).trim()
    } catch {
      return
    }
    disableInFlight.current = true
    setDisableSubmitting(true)
    try {
      await patchTenant(disabling.id, { status: 'disabled', reason })
      message.success(`企业 ${disabling.name} 已禁用`)
      setDisabling(null)
      disableForm.resetFields()
      load()
    } catch (e) {
      message.error(apiErrorMessage(e, '禁用失败'))
    } finally {
      disableInFlight.current = false
      setDisableSubmitting(false)
    }
  }

  const columns: ColumnsType<TenantRow> = [
    { title: 'Slug', dataIndex: 'slug', render: (v: string) => <Text code>{v}</Text> },
    { title: '企业名称', dataIndex: 'name' },
    {
      title: '状态', dataIndex: 'status', width: 100,
      render: (v: string) => <Tag color={STATUS_COLORS[v] || 'default'}>{STATUS_LABELS[v] || v}</Tag>,
    },
    {
      title: '配额（并发/存储/Tokens）', width: 220,
      render: (_: unknown, row: TenantRow) => (
        // 未单独设置 = 按套餐默认配额（注册即挂免费档），不是「无限制」
        !row.quota || Object.keys(row.quota).length === 0 ? <Text type="secondary">默认配额</Text> : (
          <Text>
            {row.quota.task_concurrency ?? '默认'} / {row.quota.result_storage ?? '默认'} / {row.quota.llm_tokens_month ?? '默认'}
          </Text>
        )
      ),
    },
    {
      title: '到期时间', dataIndex: 'expires_at', width: 150,
      render: (v: string | null) => formatDate(v, '不过期'),
    },
    {
      title: '操作', width: 230,
      render: (_: unknown, row: TenantRow) => (
        <Space size={4}>
          {!PROTECTED_SLUGS.has(row.slug) && (
            <Button size="small" onClick={() => {
              grantForm.setFieldsValue({ product: 'plan_enterprise', periods: 12, amount_yuan: undefined, note: '' })
              setGranting(row)
            }}>开通套餐</Button>
          )}
          {PROTECTED_SLUGS.has(row.slug) ? (
            <Tag>受保护</Tag>
          ) : row.status === 'active' ? (
            <Button size="small" danger onClick={() => { disableForm.resetFields(); setDisabling(row) }}>
              禁用
            </Button>
          ) : (
            <Popconfirm title={`确认启用企业 ${row.name}？`} okText="启用" cancelText="取消"
                        onConfirm={() => onEnable(row)}>
              <Button size="small">启用</Button>
            </Popconfirm>
          )}
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
        title={`共 ${total} 条死信（最新在前）`}
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
             title="平台运营台为平台超管专属；到期租户会被登录拒绝（可行动文案），此处可续期/调整套餐" />
      <Space style={{ marginBottom: 12 }}>
        <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
      </Space>
      <Table rowKey="id" size="middle" loading={loading} columns={columns} dataSource={rows} pagination={false} />

              </>
            ),
          },
          { key: 'dead-items', label: '死信队列', children: <DeadItemsTab /> },
          { key: 'orders', label: '待确认收款', children: <PendingOrdersTab /> },
          { key: 'product-events', label: '产品事实', children: <ProductEvents /> },
        ]}
      />

      <Modal
        title={`开通套餐：${granting?.name ?? ''}`}
        open={!!granting}
        onOk={onConfirmGrant}
        onCancel={() => { if (!grantSubmitting) setGranting(null) }}
        okText="确认开通"
        cancelText="取消"
        okButtonProps={{ loading: grantSubmitting }}
        maskClosable={false}
      >
        <Alert type="info" showIcon style={{ marginBottom: 12 }}
               title="成交后开通：记一笔线下已收款订单（合同金额），按期数开通套餐；企业档附带中转。" />
        <Form form={grantForm} layout="vertical">
          <Form.Item name="product" label="套餐" rules={[{ required: true }]}>
            <Select options={[
              { value: 'plan_enterprise', label: '企业档' },
              { value: 'plan_pro', label: '专业档' },
            ]} />
          </Form.Item>
          <Form.Item name="periods" label="期数（月）" rules={[{ required: true, message: '请填写期数' }]}>
            <InputNumber min={1} max={36} precision={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="amount_yuan" label="合同金额（元）" rules={[{ required: true, message: '请填写合同金额' }]}>
            <InputNumber min={0} precision={2} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="note" label="备注">
            <Input maxLength={200} placeholder="合同号等，记入审计" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`禁用企业：${disabling?.name ?? ''}`}
        open={!!disabling}
        onOk={onConfirmDisable}
        onCancel={() => { if (!disableSubmitting) setDisabling(null) }}
        okText="确认禁用"
        cancelText="取消"
        okButtonProps={{ danger: true, loading: disableSubmitting }}
        cancelButtonProps={{ disabled: disableSubmitting }}
        maskClosable={false}
      >
        <Alert type="warning" showIcon style={{ marginBottom: 12 }}
               title="禁用后该企业全部成员将无法登录后台；可随时重新启用。" />
        <Form form={disableForm} layout="vertical">
          <Form.Item name="reason" label="禁用原因（记入操作日志）"
                     rules={[{ required: true, whitespace: true, message: '请填写禁用原因' }]}>
            <Input.TextArea rows={3} maxLength={200} showCount placeholder="填写禁用原因，如：长期欠费、违规使用" />
          </Form.Item>
        </Form>
      </Modal>

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
