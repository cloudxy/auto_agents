/**
 * 企业管理（SaaS 化）：租户（公司）CRUD + 部门组织树
 *
 * 与平台运营台的分工：运营台管套餐/配额/到期；本页管组织结构（公司与部门），
 * 部门用于资源分配粒度（中转站渠道/虚拟 Key 的公司→部门→个人链路）。
 */
import React, { useCallback, useEffect, useState } from 'react'
import {
  Button, Card, Form, Input, message, Modal, Popconfirm, Select, Space,
  Table, Tabs, Tag, Typography,
} from 'antd'
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import {
  createDepartment, deleteDepartment, listDepartments,
  type DepartmentRow,
} from '../services/rbac'
import { createTenantMinimal, listTenants, type TenantRow } from '../services/enterprise'
import { apiErrorMessage } from '../utils/errorMessage'

const { Text } = Typography

// ---------------- 部门管理 ----------------
const DepartmentsTab: React.FC = () => {
  const [tenants, setTenants] = useState<TenantRow[]>([])
  const [tenantId, setTenantId] = useState<number | null>(null)
  const [rows, setRows] = useState<DepartmentRow[]>([])
  const [loading, setLoading] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [form] = Form.useForm()

  const load = useCallback(async (tid: number) => {
    setLoading(true)
    try {
      setRows(await listDepartments(tid))
    } catch (e) {
      message.error(apiErrorMessage(e, '部门列表加载失败'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    listTenants().then((ts) => {
      setTenants(ts)
      if (ts.length) { setTenantId(ts[0].id); load(ts[0].id) }
    }).catch(() => setTenants([]))
  }, [load])

  const onCreate = async () => {
    if (!tenantId) return
    try {
      const values = await form.validateFields()
      await createDepartment({ tenant_id: tenantId, ...values })
      message.success(`部门「${values.name}」已创建`)
      setCreateOpen(false)
      form.resetFields()
      load(tenantId)
    } catch (e) {
      if ((e as { errorFields?: unknown })?.errorFields) return
      message.error(apiErrorMessage(e, '创建部门失败'))
    }
  }

  const onDelete = async (d: DepartmentRow) => {
    if (!tenantId) return
    try {
      await deleteDepartment(d.id)
      message.success(`部门「${d.name}」已删除（成员回退未分组）`)
      load(tenantId)
    } catch (e) {
      message.error(apiErrorMessage(e, '删除部门失败'))
    }
  }

  return (
    <div>
      <Space style={{ marginBottom: 16 }} wrap>
        <Text type="secondary">公司：</Text>
        <select
          value={tenantId ?? undefined}
          onChange={(e) => { const v = Number(e.target.value); setTenantId(v); load(v) }}
          style={{ padding: '4px 8px', borderRadius: 6, border: '1px solid #d9d9d9' }}
        >
          {tenants.map((t) => <option key={t.id} value={t.id}>{t.name}（{t.slug}）</option>)}
        </select>
        <Button icon={<ReloadOutlined />} onClick={() => tenantId && load(tenantId)}>刷新</Button>
        <Button type="primary" icon={<PlusOutlined />} disabled={!tenantId} onClick={() => setCreateOpen(true)}>新建部门</Button>
      </Space>
      <Table
        rowKey="id" size="small" loading={loading} dataSource={rows} pagination={false}
        columns={[
          { title: 'ID', dataIndex: 'id', width: 60 },
          { title: '部门名', dataIndex: 'name', render: (v: string) => <Text strong>{v}</Text> },
          { title: '说明', dataIndex: 'description', ellipsis: true, render: (v: string | null) => v || '-' },
          { title: '成员数', dataIndex: 'member_count', width: 90 },
          { title: '操作', width: 90, render: (_: unknown, r: DepartmentRow) => (
            <Popconfirm title={`确认删除部门「${r.name}」？成员将回退为未分组。`}
                        okText="删除" okButtonProps={{ danger: true }} cancelText="取消" onConfirm={() => onDelete(r)}>
              <Button type="link" danger size="small">删除</Button>
            </Popconfirm>
          )},
        ]}
      />
      <Modal title="新建部门" open={createOpen} onOk={onCreate} onCancel={() => setCreateOpen(false)}
             okText="创建" cancelText="取消">
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="部门名" rules={[{ required: true, message: '请输入部门名' }]}>
            <Input placeholder="如：数据组" allowClear />
          </Form.Item>
          <Form.Item name="description" label="说明">
            <Input placeholder="职责说明（可选）" allowClear />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}


// ---------------- 公司（租户）管理 ----------------
const TenantsTab: React.FC = () => {
  const [rows, setRows] = useState<TenantRow[]>([])
  const [loading, setLoading] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [form] = Form.useForm()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setRows(await listTenants())
    } catch (e) {
      message.error(apiErrorMessage(e, '公司列表加载失败'))
    } finally {
      setLoading(false)
    }
  }, [])
  useEffect(() => { load() }, [load])

  const onCreate = async () => {
    try {
      const values = await form.validateFields()
      await createTenantMinimal(values)
      message.success(`公司「${values.name}」已创建`)
      setCreateOpen(false)
      form.resetFields()
      load()
    } catch (e) {
      if ((e as { errorFields?: unknown })?.errorFields) return
      message.error(apiErrorMessage(e, '创建公司失败'))
    }
  }

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>新建公司</Button>
      </Space>
      <Table rowKey="id" size="small" loading={loading} dataSource={rows} pagination={false}
             columns={[
               { title: 'ID', dataIndex: 'id', width: 60 },
               { title: '公司名', dataIndex: 'name', render: (v: string) => <Text strong>{v}</Text> },
               { title: '标识', dataIndex: 'slug', render: (v: string) => <Text code>{v}</Text> },
               { title: '状态', dataIndex: 'status', width: 90,
                 render: (v: string) => <Tag color={v === 'active' ? 'success' : v === 'disabled' ? 'warning' : 'error'}>{v}</Tag> },
               { title: '到期', dataIndex: 'expires_at', width: 110,
                 render: (v: string | null) => (v ? new Date(v).toLocaleDateString('zh-CN') : '不过期') },
             ]} />
      <Modal title="新建公司（租户）" open={createOpen} onOk={onCreate} onCancel={() => setCreateOpen(false)}
             okText="创建" cancelText="取消">
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="公司名" rules={[{ required: true, min: 2 }]}>
            <Input placeholder="如 上海云枢科技" allowClear />
          </Form.Item>
          <Form.Item name="slug" label="标识（唯一，留空自动生成）">
            <Input placeholder="yunshu" allowClear />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

const EnterpriseManagement: React.FC = () => (
  <Card title="企业管理">
    <Tabs
      defaultActiveKey="tenants"
      items={[
        { key: 'tenants', label: '公司管理', children: <TenantsTab /> },
        { key: 'departments', label: '部门管理', children: <DepartmentsTab /> },
      ]}
    />
  </Card>
)

export default EnterpriseManagement
