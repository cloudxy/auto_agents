/**
 * 企业管理（SaaS 化）：租户（公司）CRUD + 部门组织树
 *
 * 与平台运营台的分工：运营台管套餐/配额/到期；本页管组织结构（公司与部门），
 * 部门用于资源分配粒度（中转站渠道/虚拟 Key 的公司→部门→个人链路）。
 *
 * T-28 / FR-95 增强（公司 tab）：平台默认租户「默认归属」标注（GWT-95.3）、
 * 改名（冲突 400 句原样呈现，GWT-95.1）、停用/再启用双向（GWT-95.2/95.7）、
 * 平台租户守卫句旁注（GWT-94.2/94.3，入口禁用）、列表失败≠空（GWT-95.5，T-17
 * LoadState 复用）与空态句。写动作与运营台同打 PATCH /admin/tenants/{id}
 * （tenant_admin_service 单点）——一处写、两处同显（同真相）。
 */
import React, { useCallback, useEffect, useState } from 'react'
import {
  Button, Card, Empty, Form, Input, message, Modal, Popconfirm, Space,
  Table, Tabs, Tag, Typography,
} from 'antd'
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import {
  createDepartment, deleteDepartment, listDepartments,
  type DepartmentRow,
} from '../services/rbac'
import {
  createTenantMinimal, listTenants, renameTenant, setTenantStatus,
  type TenantRow,
} from '../services/enterprise'
import { LoadFailure } from '../components/LoadState'
import { apiErrorMessage, isFormValidateError } from '../utils/errorMessage'

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

/** 账户状态中文标签（edge-states 企业管理屏：行状态「已停用」等，GWT-95.2/95.7 同显口径） */
const TENANT_STATUS: Record<string, { text: string; color: string }> = {
  active: { text: '启用', color: 'success' },
  disabled: { text: '已停用', color: 'warning' },
  expired: { text: '已到期', color: 'error' },
}

/** 离线钉句（edge-states 企业管理屏）：改名/停用/启用都不发请求 */
const OFFLINE_SAVE_SENTENCE = '网络不可用，企业信息没有保存。'

/** 改名冲突 400 句前缀（T-27 后端单源句「企业名称不可用: {name}」） */
const NAME_CONFLICT_PREFIX = '企业名称不可用'

/** 改名错误态：后端句原样行 + 可选 edge-states 内联句行 */
interface RenameError {
  backend: string
  attempted: string | null
}

const TenantsTab: React.FC = () => {
  const [rows, setRows] = useState<TenantRow[]>([])
  const [loading, setLoading] = useState(false)
  const [listError, setListError] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [renaming, setRenaming] = useState<TenantRow | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [renameError, setRenameError] = useState<RenameError | null>(null)
  const [createForm] = Form.useForm()
  const [renameForm] = Form.useForm()

  const load = useCallback(async () => {
    setLoading(true)
    setListError(false)
    try {
      setRows(await listTenants()) // 与运营台同一数据源（GET /admin/tenants）
    } catch {
      setListError(true) // FR-84：失败≠空表（GWT-95.5）
    } finally {
      setLoading(false)
    }
  }, [])
  useEffect(() => { load() }, [load])

  const onCreate = async () => {
    try {
      const values = await createForm.validateFields()
      await createTenantMinimal(values)
      message.success(`公司「${values.name}」已创建`)
      setCreateOpen(false)
      createForm.resetFields()
      load()
    } catch (e) {
      if (isFormValidateError(e)) return
      message.error(apiErrorMessage(e, '创建公司失败'))
    }
  }

  // 改名（GWT-95.1）：确认弹窗；冲突 400 句原样呈现、弹窗不关（P-FE-05 口径）
  const openRename = (t: TenantRow) => {
    setRenaming(t)
    setRenameError(null)
    renameForm.setFieldsValue({ name: t.name })
  }

  const onRename = async () => {
    if (!renaming) return
    if (typeof navigator !== 'undefined' && !navigator.onLine) {
      setRenameError({ backend: OFFLINE_SAVE_SENTENCE, attempted: null })
      return
    }
    let name = ''
    try {
      const values = await renameForm.validateFields()
      name = values.name
      setSubmitting(true)
      await renameTenant(renaming.id, name)
      message.success('企业名称已更新。')
      setRenaming(null)
      load() // 同一真相：本页与运营台同读 /admin/tenants，刷新后两处同显新名
    } catch (e) {
      if (isFormValidateError(e)) return
      const backend = apiErrorMessage(e, '')
      setRenameError(backend.startsWith(NAME_CONFLICT_PREFIX)
        ? { backend, attempted: name || renaming.name }
        : { backend: `企业信息保存失败。${backend || '检查网络后重试'}。`, attempted: null })
    } finally {
      setSubmitting(false)
    }
  }

  // 账户状态双向流转（GWT-95.2/95.7）：停用带后果确认；平台租户入口禁用、后端守卫兜底
  const onSetStatus = async (t: TenantRow, status: 'active' | 'disabled') => {
    if (typeof navigator !== 'undefined' && !navigator.onLine) {
      message.error(OFFLINE_SAVE_SENTENCE)
      return
    }
    try {
      await setTenantStatus(t.id, status)
      message.success(status === 'disabled' ? '企业已停用。' : '企业已启用。')
      load()
    } catch (e) {
      message.error(`企业信息保存失败。${apiErrorMessage(e, '') || '检查网络后重试'}。`)
    }
  }

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    {
      title: '公司名', dataIndex: 'name',
      render: (v: string, r: TenantRow) => (
        <Space size={4} wrap>
          <Text strong>{v}</Text>
          {r.is_platform_default && <Tag color="blue">默认归属</Tag>}
        </Space>
      ),
    },
    { title: '标识', dataIndex: 'slug', render: (v: string) => <Text code>{v}</Text> },
    {
      title: '状态', dataIndex: 'status', width: 90,
      render: (v: string) => {
        const s = TENANT_STATUS[v] || { text: v, color: 'default' }
        return <Tag color={s.color}>{s.text}</Tag>
      },
    },
    { title: '到期', dataIndex: 'expires_at', width: 110,
      render: (v: string | null) => (v ? new Date(v).toLocaleDateString('zh-CN') : '不过期') },
    {
      // 平台租户（GWT-94.2/94.3）：改名/停用入口禁用 + 守卫句旁注；无删除企业控件（GWT-94.4）
      title: '操作', width: 210,
      render: (_: unknown, r: TenantRow) => r.is_platform_default ? (
        <Space orientation="vertical" size={2}>
          <Space size={0}>
            <Button type="link" size="small" disabled>改名</Button>
            <Button type="link" size="small" danger disabled>停用</Button>
          </Space>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {/* 两句钉句各占一个元素：可被精确断言/朗读各自成句（UsersRestore 同款） */}
            <span style={{ display: 'block' }}>平台租户不可修改名称。</span>
            <span style={{ display: 'block' }}>平台租户不可停用。</span>
          </Text>
        </Space>
      ) : (
        <Space size={0}>
          <Button type="link" size="small" onClick={() => openRename(r)}>改名</Button>
          {r.status === 'active' ? (
            <Popconfirm
              title={`停用 “${r.name}”？`}
              description="停用后该企业用户将无法登录。"
              okText="停用" okButtonProps={{ danger: true }} cancelText="取消"
              onConfirm={() => onSetStatus(r, 'disabled')}
            >
              <Button type="link" danger size="small">停用</Button>
            </Popconfirm>
          ) : (
            <Button type="link" size="small" onClick={() => onSetStatus(r, 'active')}>启用</Button>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>新建公司</Button>
      </Space>
      {listError ? (
        <LoadFailure title="企业列表加载失败。检查网络后重试。" onRetry={load} />
      ) : (
        <Table
          rowKey="id" size="small" loading={loading} dataSource={rows} pagination={false}
          locale={{
            emptyText: (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE}
                     description="还没有企业。新建后出现在这里，可修改名称与账户状态。" />
            ),
          }}
          columns={columns}
        />
      )}
      <Modal title="新建公司（租户）" open={createOpen} onOk={onCreate} onCancel={() => setCreateOpen(false)}
             okText="创建" cancelText="取消">
        <Form form={createForm} layout="vertical">
          <Form.Item name="name" label="公司名" rules={[{ required: true, min: 2 }]}>
            <Input placeholder="如 上海云枢科技" allowClear />
          </Form.Item>
          <Form.Item name="slug" label="标识（唯一，留空自动生成）">
            <Input placeholder="yunshu" allowClear />
          </Form.Item>
        </Form>
      </Modal>
      <Modal
        title="修改企业名称" open={!!renaming} onOk={onRename} onCancel={() => setRenaming(null)}
        confirmLoading={submitting} okText="保存" cancelText="取消"
      >
        <p>保存后企业管理页与平台运营台同显新名称。</p>
        <Form form={renameForm} layout="vertical">
          <Form.Item name="name" label="企业名称" rules={[{ required: true, min: 2, message: '公司名至少 2 个字符' }]}>
            <Input placeholder="如 上海云枢科技" allowClear />
          </Form.Item>
        </Form>
        {renameError && (
          <Typography.Paragraph type="danger" role="alert">
            <span style={{ display: 'block' }}>{renameError.backend}</span>
            {renameError.attempted && (
              <span style={{ display: 'block' }}>“{renameError.attempted}”与现有企业或保留名冲突，请更换名称。</span>
            )}
          </Typography.Paragraph>
        )}
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
