/**
 * 组织与角色管理（SaaS 化）：角色权限矩阵 + 部门组织树
 *
 * - 角色 Tab：每角色一行 × 权限码目录勾选（menu:* 菜单可见性 + btn:* 按钮级），
 *   保存即 DB 单源生效（/auth/permissions 实时读取，用户重登/刷新即得新权限）
 * - 部门 Tab：按公司管理部门（软删除），成员挂接在用户管理页
 */
import React, { useCallback, useEffect, useState } from 'react'
import { Select, Switch,
  Alert, Button, Card, Checkbox, Form, Input, message, Modal, Popconfirm,
  Space, Spin, Table, Tabs, Tag, Typography,
} from 'antd'
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import {
  createMenu, createPermissionResource, createRole, deleteMenu, deletePermissionResource,
  deleteRole, fetchMenuTree, listPermissionResources, listRoles, updateMenu, updateRole,
  type MenuNode, type PermissionCode, type PermissionRow, type RoleRow,
} from '../services/rbac'
import { listTenants, type TenantRow } from '../services/platformOps'
import { apiErrorMessage } from '../utils/errorMessage'

const { Text } = Typography

// ---------------- 角色权限矩阵 ----------------
const RolesTab: React.FC = () => {
  const [roles, setRoles] = useState<RoleRow[]>([])
  const [catalog, setCatalog] = useState<PermissionCode[]>([])
  const [loading, setLoading] = useState(true)
  const [savingKey, setSavingKey] = useState<string | null>(null)
  // 本地编辑态：role_key → 权限码集合
  const [drafts, setDrafts] = useState<Record<string, string[]>>({})

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await listRoles()
      setRoles(data.roles)
      setCatalog(data.catalog)
      setDrafts(Object.fromEntries(data.roles.map((r) => [r.role_key, [...r.permissions]])))
    } catch (e) {
      message.error(apiErrorMessage(e, '角色列表加载失败'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const toggle = (roleKey: string, code: string, checked: boolean) => {
    setDrafts((prev) => {
      const set = new Set(prev[roleKey] || [])
      checked ? set.add(code) : set.delete(code)
      return { ...prev, [roleKey]: Array.from(set) }
    })
  }

  const groupBy = catalog.reduce<Record<string, PermissionCode[]>>((acc, c) => {
    ;(acc[c.group] = acc[c.group] || []).push(c)
    return acc
  }, {})

  const save = async (role: RoleRow) => {
    try {
      setSavingKey(role.role_key)
      await updateRole(role.role_key, { permissions: drafts[role.role_key] || [] })
      message.success(`角色「${role.name}」权限已保存（即时生效）`)
      load()
    } catch (e) {
      message.error(apiErrorMessage(e, '保存角色权限失败'))
    } finally {
      setSavingKey(null)
    }
  }

  if (loading) return <div style={{ textAlign: 'center', padding: 64 }}><Spin /></div>

  const dirty = (r: RoleRow) =>
    JSON.stringify((drafts[r.role_key] || []).slice().sort()) !== JSON.stringify(r.permissions.slice().sort())

  return (
    <div>
      <Alert
        type="info" showIcon style={{ marginBottom: 16 }}
        message="权限矩阵即菜单管理"
        description="勾选即分配：menu:* 控制左侧菜单与页面可见性，btn:* 控制页面内按钮。保存后用户刷新页面即生效（权限从数据库实时读取）。"
      />
      {roles.map((role) => (
        <Card
          key={role.role_key}
          size="small"
          style={{ marginBottom: 12 }}
          title={<Space><Text strong>{role.name}</Text><Tag>{role.role_key}</Tag>{role.is_builtin && <Tag color="blue">内置</Tag>}</Space>}
          extra={
            <Space>
              <Text type="secondary">{(drafts[role.role_key] || []).length} 项权限</Text>
              <Button size="small" type="primary" disabled={!dirty(role)}
                      loading={savingKey === role.role_key} onClick={() => save(role)}>
                保存{dirty(role) ? '' : '（无变更）'}
              </Button>
            </Space>
          }
        >
          {Object.entries(groupBy).map(([group, codes]) => (
            <div key={group} style={{ marginBottom: 8 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>{group}：</Text>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 16px', marginTop: 4 }}>
                {codes.map((c) => (
                  <Checkbox
                    key={c.code}
                    checked={(drafts[role.role_key] || []).includes(c.code)}
                    onChange={(e) => toggle(role.role_key, c.code, e.target.checked)}
                  >
                    {c.label} <Text type="secondary" code style={{ fontSize: 11 }}>{c.code}</Text>
                  </Checkbox>
                ))}
              </div>
            </div>
          ))}
        </Card>
      ))}
    </div>
  )
}

// ---------------- 权限资源管理 ----------------
const PermissionsTab: React.FC = () => {
  const [rows, setRows] = useState<PermissionRow[]>([])
  const [loading, setLoading] = useState(true)
  const [createOpen, setCreateOpen] = useState(false)
  const [form] = Form.useForm()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setRows(await listPermissionResources())
    } catch (e) {
      message.error(apiErrorMessage(e, '权限资源加载失败'))
    } finally {
      setLoading(false)
    }
  }, [])
  useEffect(() => { load() }, [load])

  const onCreate = async () => {
    try {
      const values = await form.validateFields()
      await createPermissionResource(values)
      message.success(`权限码 ${values.code} 已注册`)
      setCreateOpen(false)
      form.resetFields()
      load()
    } catch (e) {
      if ((e as { errorFields?: unknown })?.errorFields) return
      message.error(apiErrorMessage(e, '注册权限码失败'))
    }
  }

  const onDelete = async (r: PermissionRow) => {
    try {
      await deletePermissionResource(Number(r.id))
      message.success(`权限码 ${r.code} 已删除`)
      load()
    } catch (e) {
      message.error(apiErrorMessage(e, '删除失败（可能仍被角色引用）'))
    }
  }

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>注册权限码</Button>
      </Space>
      <Table rowKey="code" size="small" loading={loading} dataSource={rows} pagination={false}
             columns={[
               { title: '权限码', dataIndex: 'code', render: (v: string) => <Text code>{v}</Text> },
               { title: '名称', dataIndex: 'name' },
               { title: '分组', dataIndex: 'group', width: 110, render: (v: string) => <Tag>{v}</Tag> },
               { title: '类型', dataIndex: 'ptype', width: 80, render: (v?: string) => <Tag color={v === 'menu' ? 'blue' : 'green'}>{v || 'btn'}</Tag> },
               { title: '说明', dataIndex: 'description', ellipsis: true, render: (v: string | null) => v || '-' },
               { title: '操作', width: 80, render: (_: unknown, r: PermissionRow) => (
                 <Popconfirm title={`删除权限码 ${r.code}？`} okText="删除" okButtonProps={{ danger: true }} cancelText="取消"
                             onConfirm={() => onDelete(r)}>
                   <Button type="link" danger size="small">删除</Button>
                 </Popconfirm>
               )},
             ]} />
      <Modal title="注册权限码" open={createOpen} onOk={onCreate} onCancel={() => setCreateOpen(false)}
             okText="注册" cancelText="取消">
        <Form form={form} layout="vertical" initialValues={{ ptype: 'btn', group_name: '自定义' }}>
          <Form.Item name="code" label="权限码" rules={[{ required: true, pattern: /^(menu|btn|api):[a-z0-9_.:-]+$/, message: '格式 menu:*/btn:*/api:* 小写' }]}>
            <Input placeholder="如 btn:report:export" allowClear />
          </Form.Item>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input placeholder="如 导出报表" allowClear />
          </Form.Item>
          <Form.Item name="ptype" label="类型">
            <Select options={[{ value: 'btn', label: '按钮' }, { value: 'menu', label: '菜单' }, { value: 'api', label: 'API' }]} />
          </Form.Item>
          <Form.Item name="group_name" label="分组">
            <Input allowClear />
          </Form.Item>
          <Form.Item name="description" label="说明">
            <Input allowClear />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

// ---------------- 菜单管理 ----------------
const MenusTab: React.FC = () => {
  const [tree, setTree] = useState<MenuNode[]>([])
  const [loading, setLoading] = useState(true)
  const [createOpen, setCreateOpen] = useState(false)
  const [editing, setEditing] = useState<MenuNode | null>(null)
  const [form] = Form.useForm()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setTree(await fetchMenuTree())
    } catch (e) {
      message.error(apiErrorMessage(e, '菜单树加载失败'))
    } finally {
      setLoading(false)
    }
  }, [])
  useEffect(() => { load() }, [load])

  const openCreate = (parent?: MenuNode) => {
    form.resetFields()
    form.setFieldsValue({ parent_id: parent?.id ?? null, sort_order: 100 })
    setCreateOpen(true)
  }
  const onCreate = async () => {
    try {
      const values = await form.validateFields()
      await createMenu(values)
      message.success(`菜单「${values.name}」已创建（刷新页面生效）`)
      setCreateOpen(false)
      load()
    } catch (e) {
      if ((e as { errorFields?: unknown })?.errorFields) return
      message.error(apiErrorMessage(e, '创建菜单失败'))
    }
  }
  const openEdit = (m: MenuNode) => {
    setEditing(m)
    form.setFieldsValue({ name: m.name, path: m.path, icon: m.icon, permission: m.permission, sort_order: m.sort_order, visible: m.visible })
  }
  const onEdit = async () => {
    if (!editing) return
    try {
      const values = await form.validateFields()
      await updateMenu(editing.id, values)
      message.success('菜单已更新（刷新页面生效）')
      setEditing(null)
      load()
    } catch (e) {
      if ((e as { errorFields?: unknown })?.errorFields) return
      message.error(apiErrorMessage(e, '更新菜单失败'))
    }
  }
  const onDelete = async (m: MenuNode) => {
    try {
      await deleteMenu(m.id)
      message.success(`菜单「${m.name}」已删除（刷新页面生效）`)
      load()
    } catch (e) {
      message.error(apiErrorMessage(e, '删除失败（可能有子菜单）'))
    }
  }

  const columns = [
    { title: '排序', dataIndex: 'sort_order', width: 70 },
    { title: '菜单名', dataIndex: 'name', render: (v: string, r: MenuNode) => (
      <Space>
        <Text strong={r.parent_id === null}>{v}</Text>
        {!r.visible && <Tag color="red">已隐藏</Tag>}
        {r.path && <Text code style={{ fontSize: 12 }}>{r.path}</Text>}
      </Space>
    )},
    { title: '路由', dataIndex: 'path', width: 150, render: (v: string | null) => v || <Tag>分组</Tag> },
    { title: '权限码', dataIndex: 'permission', width: 170, render: (v: string | null) => v ? <Text code style={{ fontSize: 12 }}>{v}</Text> : <Text type="secondary">登录可见</Text> },
    { title: '操作', width: 200, render: (_: unknown, r: MenuNode) => (
      <Space size={0}>
        <Button type="link" size="small" onClick={() => openCreate(r)}>加子项</Button>
        <Button type="link" size="small" onClick={() => openEdit(r)}>编辑</Button>
        <Popconfirm title={`删除菜单「${r.name}」？`} okText="删除" okButtonProps={{ danger: true }} cancelText="取消"
                    onConfirm={() => onDelete(r)}>
          <Button type="link" danger size="small">删除</Button>
        </Popconfirm>
      </Space>
    )},
  ]

  return (
    <div>
      <Alert type="info" showIcon style={{ marginBottom: 16 }}
             message="菜单结构在此维护（menus 表为运行时真相源）"
             description="新建/编辑/删除后刷新页面生效；权限码控制可见性，空=登录即可见。左侧导航由 /auth/menus 按当前用户权限动态下发。" />
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => openCreate()}>新建顶级菜单</Button>
      </Space>
      <Table rowKey="id" size="small" loading={loading} columns={columns}
             dataSource={tree}
             pagination={false}
             expandable={{ defaultExpandAllRows: true, childrenColumnName: 'children' }} />
      <Modal title="新建菜单" open={createOpen} onOk={onCreate} onCancel={() => setCreateOpen(false)} okText="创建" cancelText="取消">
        <Form form={form} layout="vertical">
          <Form.Item name="parent_id" label="父菜单 ID（空=顶级）">
            <Input type="number" placeholder="留空=顶级分组" />
          </Form.Item>
          <Form.Item name="name" label="菜单名" rules={[{ required: true }]}>
            <Input placeholder="如 报表中心" allowClear />
          </Form.Item>
          <Form.Item name="path" label="路由" tooltip="分组菜单留空；路由菜单须与前端页面路由一致">
            <Input placeholder="/reports" allowClear />
          </Form.Item>
          <Form.Item name="icon" label="图标标识">
            <Input placeholder="DashboardOutlined / BugOutlined / AppstoreOutlined …" allowClear />
          </Form.Item>
          <Form.Item name="permission" label="权限码" tooltip="控制可见性；留空=登录可见">
            <Input placeholder="menu:reports" allowClear />
          </Form.Item>
          <Form.Item name="sort_order" label="排序" initialValue={100}>
            <Input type="number" />
          </Form.Item>
        </Form>
      </Modal>
      <Modal title={`编辑菜单：${editing?.name ?? ''}`} open={!!editing} onOk={onEdit} onCancel={() => setEditing(null)} okText="保存" cancelText="取消">
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="菜单名" rules={[{ required: true }]}>
            <Input allowClear />
          </Form.Item>
          <Form.Item name="path" label="路由">
            <Input allowClear />
          </Form.Item>
          <Form.Item name="icon" label="图标标识">
            <Input allowClear />
          </Form.Item>
          <Form.Item name="permission" label="权限码">
            <Input allowClear />
          </Form.Item>
          <Form.Item name="sort_order" label="排序">
            <Input type="number" />
          </Form.Item>
          <Form.Item name="visible" label="启用" valuePropName="checked">
            <Switch checkedChildren="显示" unCheckedChildren="隐藏" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

const RbacManagement: React.FC = () => (
  <Card title="角色权限菜单管理">
    <Tabs
      defaultActiveKey="roles"
      items={[
        { key: 'roles', label: '角色管理', children: <RolesTab /> },
        { key: 'permissions', label: '权限管理', children: <PermissionsTab /> },
        { key: 'menus', label: '菜单管理', children: <MenusTab /> },
      ]}
    />
  </Card>
)

export default RbacManagement

