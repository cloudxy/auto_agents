/**
 * 用户管理页（平台超管）：增删改查 + 角色分配 + 公司归属
 *
 * 权限语义：role 单源（admin/operator/viewer → 后端 _ROLE_PERMISSIONS 下发）；
 * 归属公司 Select 数据源 /admin/tenants；防自锁（不可降级/停用/删除自己）由后端守卫。
 */
import React, { useEffect, useState } from 'react'
import {
  Avatar, Button, Card, Form, Input, message, Modal, Popconfirm, Select,
  Space, Switch, Table, Tag,
} from 'antd'
import { PlusOutlined, UserOutlined } from '@ant-design/icons'
import { fetchUsersPage } from '../services/admin'
import {
  createUser, deleteUser, updateUser,
  type UserCreatePayload, type UserItem, type UserUpdatePayload,
} from '../services/users'
import { listTenants, type TenantRow } from '../services/platformOps'
import { apiErrorMessage } from '../utils/errorMessage'

const ROLE_OPTIONS = [
  { value: 'admin', label: '管理员（全权）' },
  { value: 'operator', label: '操作员（创建/运行）' },
  { value: 'viewer', label: '只读' },
]

const Users: React.FC = () => {
  const [loading, setLoading] = useState(false)
  const [users, setUsers] = useState<UserItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const pageSize = 20
  const [tenants, setTenants] = useState<TenantRow[]>([])
  // 弹窗态
  const [createOpen, setCreateOpen] = useState(false)
  const [editing, setEditing] = useState<UserItem | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [createForm] = Form.useForm()
  const [editForm] = Form.useForm()

  const loadUsers = async (p: number) => {
    setLoading(true)
    try {
      const res = await fetchUsersPage<UserItem>({ skip: (p - 1) * pageSize, limit: pageSize })
      setUsers(res.items || [])
      setTotal(res.total || 0)
    } catch (e) {
      message.error(apiErrorMessage(e, '获取用户列表失败'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadUsers(page)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page])

  useEffect(() => {
    listTenants().then(setTenants).catch(() => setTenants([]))
  }, [])

  const tenantOptions = [
    { value: 0, label: '（平台账户，不挂公司）' },
    ...tenants.map((t) => ({ value: t.id, label: `${t.name}（${t.slug}）` })),
  ]

  // ---------------- 创建 ----------------
  const onCreate = async () => {
    try {
      const values = await createForm.validateFields()
      setSubmitting(true)
      const payload: UserCreatePayload = {
        username: values.username, email: values.email,
        password: values.password, role: values.role || 'viewer',
        tenant_id: values.tenant_id ?? null,
      }
      if (!payload.tenant_id) payload.tenant_id = null
      await createUser(payload)
      message.success(`用户「${payload.username}」已创建`)
      setCreateOpen(false)
      createForm.resetFields()
      loadUsers(page)
    } catch (e) {
      if ((e as { errorFields?: unknown })?.errorFields) return
      message.error(apiErrorMessage(e, '创建用户失败'))
    } finally {
      setSubmitting(false)
    }
  }

  // ---------------- 编辑（角色/启停/归属） ----------------
  const openEdit = (u: UserItem) => {
    setEditing(u)
    editForm.setFieldsValue({
      role: u.role || (u.is_admin ? 'admin' : 'operator'),
      is_active: u.is_active,
      tenant_id: u.tenant_id ?? 0,
    })
  }

  const onEdit = async () => {
    if (!editing) return
    try {
      const values = await editForm.validateFields()
      setSubmitting(true)
      const payload: UserUpdatePayload = {
        role: values.role,
        is_active: values.is_active,
        tenant_id: values.tenant_id || null,
      }
      await updateUser(editing.id, payload)
      message.success(`用户「${editing.username}」已更新`)
      setEditing(null)
      loadUsers(page)
    } catch (e) {
      if ((e as { errorFields?: unknown })?.errorFields) return
      message.error(apiErrorMessage(e, '更新用户失败'))
    } finally {
      setSubmitting(false)
    }
  }

  const onDelete = async (u: UserItem) => {
    try {
      await deleteUser(u.id)
      message.success(`用户「${u.username}」已删除（软删除，审计可追溯）`)
      loadUsers(page)
    } catch (e) {
      message.error(apiErrorMessage(e, '删除用户失败'))
    }
  }

  const columns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    {
      title: '用户',
      key: 'username',
      render: (_: unknown, record: UserItem) => (
        <Space>
          <Avatar size="small" icon={<UserOutlined />} />
          {record.username}
          {record.is_platform_admin && <Tag color="purple">平台超管</Tag>}
        </Space>
      ),
    },
    { title: '邮箱', dataIndex: 'email', key: 'email', ellipsis: true },
    {
      title: '归属公司', key: 'tenant', width: 150,
      render: (_: unknown, record: UserItem) =>
        record.tenant_name ? <Tag color="geekblue">{record.tenant_name}</Tag> : <Tag>平台</Tag>,
    },
    {
      title: '角色', key: 'role', width: 100,
      render: (_: unknown, record: UserItem) => {
        const role = record.role || (record.is_admin ? 'admin' : 'operator')
        if (role === 'admin') return <Tag color="gold">管理员</Tag>
        if (role === 'viewer') return <Tag>只读</Tag>
        return <Tag color="blue">操作员</Tag>
      },
    },
    {
      title: '状态', key: 'is_active', width: 80,
      render: (_: unknown, record: UserItem) =>
        record.is_active ? <Tag color="green">激活</Tag> : <Tag color="red">停用</Tag>,
    },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 170,
      render: (v: string | null) => (v ? new Date(v).toLocaleString('zh-CN') : '-') },
    {
      title: '操作', key: 'action', width: 140,
      render: (_: unknown, record: UserItem) => (
        <Space size={0}>
          <Button type="link" size="small" onClick={() => openEdit(record)}>编辑</Button>
          <Popconfirm
            title={`确认删除用户「${record.username}」？`}
            description="软删除，操作审计可追溯。"
            okText="删除" okButtonProps={{ danger: true }} cancelText="取消"
            onConfirm={() => onDelete(record)}
          >
            <Button type="link" danger size="small">删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Card
      title={`用户管理（共 ${total} 人）`}
      extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>新建用户</Button>}
    >
      <Table
        columns={columns}
        dataSource={users}
        rowKey="id"
        loading={loading}
        pagination={{
          current: page, pageSize, total, onChange: setPage,
          showTotal: (t) => `共 ${t} 位用户`,
        }}
      />

      {/* 新建用户 */}
      <Modal
        title="新建用户" open={createOpen} onOk={onCreate} onCancel={() => setCreateOpen(false)}
        confirmLoading={submitting} okText="创建" cancelText="取消"
      >
        <Form form={createForm} layout="vertical" initialValues={{ role: 'viewer' }}>
          <Form.Item name="username" label="用户名" rules={[{ required: true, min: 3, message: '至少 3 个字符' }]}>
            <Input placeholder="如 op-zhang" allowClear />
          </Form.Item>
          <Form.Item name="email" label="邮箱" rules={[{ required: true, type: 'email', message: '邮箱不合法' }]}>
            <Input placeholder="user@company.com" allowClear />
          </Form.Item>
          <Form.Item name="password" label="初始密码" rules={[{ required: true, min: 8, message: '至少 8 位' }]}>
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Form.Item name="role" label="角色（权限分配）">
            <Select options={ROLE_OPTIONS} />
          </Form.Item>
          <Form.Item name="tenant_id" label="归属公司" tooltip="平台账户（不挂公司）+ admin 角色 = 平台超管">
            <Select options={tenantOptions} placeholder="选择公司（或平台账户）" allowClear />
          </Form.Item>
        </Form>
      </Modal>

      {/* 编辑：角色分配 / 启停 / 归属调整 */}
      <Modal
        title={`编辑用户：${editing?.username ?? ''}`}
        open={!!editing} onOk={onEdit} onCancel={() => setEditing(null)}
        confirmLoading={submitting} okText="保存" cancelText="取消"
      >
        <Form form={editForm} layout="vertical">
          <Form.Item name="role" label="角色（权限分配）">
            <Select options={ROLE_OPTIONS} />
          </Form.Item>
          <Form.Item name="tenant_id" label="归属公司">
            <Select options={tenantOptions} />
          </Form.Item>
          <Form.Item name="is_active" label="启用" valuePropName="checked">
            <Switch checkedChildren="激活" unCheckedChildren="停用" />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}

export default Users
