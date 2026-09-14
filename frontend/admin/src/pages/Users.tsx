/**
 * 用户管理页（平台超管）：增删改查 + 角色分配 + 公司归属 +「已删除」筛选/恢复（T-25/FR-93）
 *
 * 权限语义：role 单源（admin/operator/viewer → 后端 _ROLE_PERMISSIONS 下发）；
 * 归属公司 Select 数据源 /admin/tenants；防自锁（不可降级/停用/删除自己）由后端守卫。
 * 状态筛选走服务端 status 参数（active 默认不含已删 GWT-93.2 / deleted 已删筛选 GWT-93.1），
 * 搜索/角色/公司/部门保持本地过滤；恢复动作见 UsersRestore（GWT-93.3/93.4/93.9）。
 */
import React, { useEffect, useState } from 'react'
import {
  Alert, Avatar, Button, Empty, Form, Input, message, Modal, Popconfirm, Select,
  Space, Switch, Table, Tag,
} from 'antd'
import { PlusOutlined, UserOutlined } from '@ant-design/icons'
import { fetchUsersPage } from '../services/admin'
import {
  createUser, deleteUser, updateUser,
  type UserCreatePayload, type UserItem, type UserUpdatePayload,
} from '../services/users'
import { listDepartments, type DepartmentRow } from '../services/rbac'
import { listTenants, type TenantRow } from '../services/platformOps'
import { apiErrorMessage } from '../utils/errorMessage'
import RestoreUserModal from './UsersRestore'

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
  const [departments, setDepartments] = useState<DepartmentRow[]>([])
  // 列表筛选（状态=服务端 status 参数；搜索/角色/公司/部门为本地过滤）
  const [filterText, setFilterText] = useState('')
  const [filterRole, setFilterRole] = useState('all')
  const [filterTenant, setFilterTenant] = useState<number | 'all'>('all')
  const [filterDept, setFilterDept] = useState<number | 'all'>('all')
  // all=在职全部 / active=在职·激活 / disabled=在职·停用 / deleted=已删除（T-25）
  const [filterActive, setFilterActive] = useState('all')
  const deletedView = filterActive === 'deleted'
  // 弹窗态
  const [createOpen, setCreateOpen] = useState(false)
  const [editing, setEditing] = useState<UserItem | null>(null)
  const [restoring, setRestoring] = useState<UserItem | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [listError, setListError] = useState(false)
  const [createForm] = Form.useForm()
  const [editForm] = Form.useForm()

  const loadUsers = async (p: number) => {
    setLoading(true)
    setListError(false)
    try {
      // 状态筛选走服务端（GWT-93.1/93.2）：默认视图不含已删，已删筛选只含软删行
      const res = await fetchUsersPage<UserItem>({
        skip: (p - 1) * pageSize, limit: pageSize,
        status: deletedView ? 'deleted' : 'active',
      })
      setUsers(res.items || [])
      setTotal(res.total || 0)
    } catch {
      setListError(true) // FR-84：失败≠空表，页面级错误态 + 重试
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadUsers(page)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, filterActive])

  useEffect(() => {
    listTenants().then(setTenants).catch(() => setTenants([]))
  }, [])
  // 部门跟随公司筛选联动（全部公司时聚合不重复部门意义不大，清空部门筛）
  useEffect(() => {
    if (filterTenant === 'all') { setFilterDept('all'); setDepartments([]); return }
    listDepartments(filterTenant as number).then(setDepartments).catch(() => setDepartments([]))
  }, [filterTenant])

  // 无归属默认挂平台租户（GWT-95.4 显式化，T-28）：value 0 仅表单占位，提交仍归一为 null（行为不变）
  const tenantOptions = [
    { value: 0, label: '平台租户（默认归属）' },
    ...tenants.map((t) => ({ value: t.id, label: `${t.name}（${t.slug}）` })),
  ]

  const clearLocalFilters = () => {
    setFilterText('')
    setFilterRole('all')
    setFilterTenant('all')
    setFilterDept('all')
  }
  const hasLocalFilter = filterText.trim() !== '' || filterRole !== 'all'
    || filterTenant !== 'all' || filterDept !== 'all'

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
      department_id: u.department_id ?? 0,
    })
    if (u.tenant_id) {
      listDepartments(u.tenant_id).then(setDepartments).catch(() => setDepartments([]))
    }
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
        department_id: values.department_id || null,
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
        // 无归属回退显示「平台租户」（GWT-95.4；§0.4 命名收口——AutoAgents 不出现在归属列）
        record.tenant_name ? <Tag color="geekblue">{record.tenant_name}</Tag> : <Tag>平台租户</Tag>,
    },
    {
      title: '部门', dataIndex: 'department_name', width: 100,
      render: (v: string | null) => v || <Tag>未分组</Tag>,
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
      title: '状态', key: 'status', width: 80,
      render: (_: unknown, record: UserItem) => {
        if (record.deleted_at) return <Tag color="red">已删除</Tag> // GWT-93.1 已删标记
        return record.is_active ? <Tag color="green">激活</Tag> : <Tag color="red">停用</Tag>
      },
    },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 170,
      render: (v: string | null) => (v ? new Date(v).toLocaleString('zh-CN') : '-') },
    {
      title: '操作', key: 'action', width: 140,
      render: (_: unknown, record: UserItem) => {
        // 已删行：唯一动作=恢复（GWT-93.3；无编辑/删除入口）
        if (record.deleted_at) {
          return <Button type="link" size="small" onClick={() => setRestoring(record)}>恢复</Button>
        }
        return (
          <Space size={0}>
            <Button type="link" size="small" onClick={() => openEdit(record)}>编辑</Button>
            {record.username !== 'admin' && (
            <Popconfirm
              title={`确认删除用户「${record.username}」？`}
              description="软删除，操作审计可追溯。"
              okText="删除" okButtonProps={{ danger: true }} cancelText="取消"
              onConfirm={() => onDelete(record)}
            >
              <Button type="link" danger size="small">删除</Button>
            </Popconfirm>
            )}
          </Space>
        )
      },
    },
  ]

  // 空态按视图分野（edge-states 用户管理屏）：默认初始/已删筛选/本地筛选无匹配
  const emptyContent = deletedView
    ? (
      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE}
             description="还没有已删除的用户。删除的用户会保留在这里，可恢复。" />
    )
    : hasLocalFilter
      ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前筛选无匹配的用户。">
          <Button onClick={clearLocalFilters}>清除筛选</Button>
        </Empty>
      )
      : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有用户。">
          <Button type="primary" onClick={() => setCreateOpen(true)}>新建用户</Button>
        </Empty>
      )

  return (
    <>
      {/* §0.10 / GWT-99.1：页名「用户管理」唯一标题在顶栏，无页内标题卡。
          计数由分页 showTotal「共 N 位用户」同屏承担（信息不丢）；
          原 Card extra 的筛选行 + 新建保留为内容区动作行（GWT-99.3） */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
        <Space wrap>
          <Input.Search placeholder="搜索用户名/邮箱" allowClear style={{ width: 180 }}
                        value={filterText}
                        onChange={(e) => setFilterText(e.target.value)}
                        onSearch={setFilterText} />
          <Select size="small" style={{ width: 110 }} value={filterRole} onChange={setFilterRole}
                  options={[
                    { value: 'all', label: '全部角色' },
                    { value: 'admin', label: '管理员' },
                    { value: 'operator', label: '操作员' },
                    { value: 'viewer', label: '只读' },
                  ]} />
          <Select size="small" style={{ width: 130 }} value={filterTenant}
                  onChange={(v) => setFilterTenant(v)}
                  options={[
                    { value: 'all', label: '全部公司' },
                    ...tenants.map((tt) => ({ value: tt.id, label: tt.name })),
                  ]} />
          <Select size="small" style={{ width: 110 }} value={filterDept}
                  onChange={setFilterDept} disabled={filterTenant === 'all'}
                  options={[
                    { value: 'all', label: '全部部门' },
                    ...departments.map((d) => ({ value: d.id, label: d.name })),
                  ]} />
          <span data-testid="status-filter">
            <Select size="small" style={{ width: 110 }} value={filterActive}
                    onChange={(v) => { setFilterActive(v); if (page !== 1) setPage(1) }}
                    options={[
                      { value: 'all', label: '在职（全部）' },
                      { value: 'active', label: '在职·激活' },
                      { value: 'disabled', label: '已停用' },
                      { value: 'deleted', label: '已删除' },
                    ]} />
          </span>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>新建用户</Button>
        </Space>
      </div>
      {listError ? (
        <Alert
          type="error" showIcon role="alert"
          title="用户列表加载失败。检查网络后重试。"
          action={<Button onClick={() => loadUsers(page)}>重试</Button>}
        />
      ) : (
        <Table
          columns={columns}
          dataSource={users.filter((u) => {
            const kw = filterText.trim().toLowerCase()
            if (kw && !(u.username.toLowerCase().includes(kw) || (u.email || '').toLowerCase().includes(kw))) return false
            if (filterRole !== 'all' && (u.role || (u.is_admin ? 'admin' : 'operator')) !== filterRole) return false
            if (filterTenant !== 'all' && (u.tenant_id ?? null) !== (filterTenant as number)) return false
            if (filterDept !== 'all' && (u.department_id ?? null) !== (filterDept as number)) return false
            if (filterActive !== 'all' && filterActive !== 'deleted'
              && ((filterActive === 'active') !== u.is_active)) return false
            return true
          })}
          rowKey="id"
          loading={loading}
          locale={{ emptyText: emptyContent }}
          pagination={{
            current: page, pageSize, total, onChange: setPage,
            showTotal: (t) => `共 ${t} 位用户`,
          }}
        />
      )}

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
          <Form.Item name="tenant_id" label="归属公司" tooltip="不选公司时默认归属平台租户；平台租户 + admin 角色 = 平台超管">
            <Select options={tenantOptions} placeholder="选择公司（不选则归属平台租户）" allowClear />
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
          <Form.Item name="department_id" label="所属部门" tooltip="部门须属于该公司；0=未分组">
            <Select options={[
              { value: 0, label: '（未分组）' },
              ...departments.map((d) => ({ value: d.id, label: `${d.name}（${d.member_count}人）` })),
            ]} />
          </Form.Item>
          <Form.Item name="is_active" label="启用" valuePropName="checked">
            <Switch checkedChildren="激活" unCheckedChildren="停用" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 恢复软删用户（T-25 / GWT-93.3/93.4/93.9） */}
      <RestoreUserModal
        user={restoring}
        onClose={() => setRestoring(null)}
        onRestored={() => loadUsers(page)}
      />
    </>
  )
}

export default Users
