/**
 * 组织与角色管理（SaaS 化）：角色权限矩阵 + 部门组织树
 *
 * - 角色 Tab：每角色一行 × 权限码目录勾选（menu:* 菜单可见性 + btn:* 按钮级），
 *   保存即 DB 单源生效（/auth/permissions 实时读取，用户重登/刷新即得新权限）
 * - 部门 Tab：按公司管理部门（软删除），成员挂接在用户管理页
 */
import React, { useCallback, useEffect, useState } from 'react'
import {
  Alert, Button, Card, Checkbox, Form, Input, message, Modal, Popconfirm,
  Space, Spin, Table, Tabs, Tag, Typography,
} from 'antd'
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import {
  createDepartment, deleteDepartment, listDepartments, listRoles, updateRole,
  type DepartmentRow, type PermissionCode, type RoleRow,
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

const RbacManagement: React.FC = () => (
  <Card title="组织与角色管理">
    <Tabs
      defaultActiveKey="roles"
      items={[
        { key: 'roles', label: '角色权限矩阵', children: <RolesTab /> },
        { key: 'departments', label: '部门管理', children: <DepartmentsTab /> },
      ]}
    />
  </Card>
)

export default RbacManagement

