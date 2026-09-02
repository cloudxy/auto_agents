/**
 * 成员管理页（SaaS S2-2）：租户 owner/admin 自助管理子账号。
 * Users 页归平台超管（页面分叉）——本页是租户视角。
 */
import React, { useCallback, useEffect, useState } from 'react'
import {
  Alert, Button, Form, Input, Modal, Select, Space, Switch,
  Table, Tag, Typography, message,
} from 'antd'
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'

import api, { unwrap } from '../services/api'

const { Text } = Typography

interface MemberRow {
  id: number
  username: string
  email: string
  tenant_role: string
  is_active: boolean
  created_at?: string | null
}

const ROLE_COLORS: Record<string, string> = {
  owner: 'gold', admin: 'green', operator: 'blue', viewer: 'default',
}

const listMembers = (): Promise<MemberRow[]> =>
  api.get('/members').then((r) => unwrap<MemberRow[]>(r))

const createMember = (payload: Record<string, unknown>): Promise<MemberRow> =>
  api.post('/members', payload).then((r) => unwrap<MemberRow>(r))

const patchMember = (id: number, payload: Record<string, unknown>): Promise<MemberRow> =>
  api.patch(`/members/${id}`, payload).then((r) => unwrap<MemberRow>(r))

const resetPassword = (id: number, newPassword: string): Promise<void> =>
  api.post(`/members/${id}/reset-password`, { new_password: newPassword }).then(() => undefined)

const Members: React.FC = () => {
  const [rows, setRows] = useState<MemberRow[]>([])
  const [loading, setLoading] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [form] = Form.useForm()
  const [resetTarget, setResetTarget] = useState<MemberRow | null>(null)
  const [resetForm] = Form.useForm()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setRows(await listMembers())
    } catch (e) {
      message.error(`成员加载失败: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const onCreate = async () => {
    const values = await form.validateFields()
    const created = await createMember(values)
    message.success(`成员「${created.username}」已创建`)
    setCreateOpen(false)
    form.resetFields()
    load()
  }

  const onToggleActive = async (row: MemberRow, active: boolean) => {
    try {
      await patchMember(row.id, { is_active: active })
      message.success(active ? `已启用 ${row.username}` : `已禁用 ${row.username}`)
      load()
    } catch (e) {
      message.error(`操作失败: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const onRoleChange = async (row: MemberRow, role: string) => {
    try {
      await patchMember(row.id, { tenant_role: role })
      message.success(`${row.username} → ${role}`)
      load()
    } catch (e) {
      message.error(`角色变更失败: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const onReset = async () => {
    if (!resetTarget) return
    const values = await resetForm.validateFields()
    await resetPassword(resetTarget.id, values.new_password)
    message.success(`${resetTarget.username} 密码已重置`)
    setResetTarget(null)
  }

  const columns: ColumnsType<MemberRow> = [
    { title: '用户名', dataIndex: 'username', render: (v: string) => <Text strong>{v}</Text> },
    { title: '邮箱', dataIndex: 'email', ellipsis: true },
    {
      title: '租户角色', dataIndex: 'tenant_role', width: 140,
      render: (v: string, row: MemberRow) => (
        row.tenant_role === 'owner'
          ? <Tag color={ROLE_COLORS[v]}>{v}</Tag>
          : (
            <Select
              size="small" value={v} style={{ width: 110 }}
              onChange={(role) => onRoleChange(row, role)}
              options={['admin', 'operator', 'viewer'].map((r) => ({ value: r, label: r }))}
            />
          )
      ),
    },
    {
      title: '状态', dataIndex: 'is_active', width: 100,
      render: (v: boolean, row: MemberRow) => (
        row.tenant_role === 'owner'
          ? (v ? <Tag color="success">启用</Tag> : <Tag>停用</Tag>)
          : <Switch size="small" checked={v} onChange={(active) => onToggleActive(row, active)} />
      ),
    },
    {
      title: '操作', width: 120,
      render: (_: unknown, row: MemberRow) => (
        row.tenant_role === 'owner'
          ? <Text type="secondary">所有者</Text>
          : <Button size="small" type="link" onClick={() => { setResetTarget(row); resetForm.resetFields() }}>重置密码</Button>
      ),
    },
  ]

  return (
    <div>
      <Alert type="info" showIcon style={{ marginBottom: 12 }}
             message="成员管理是租户内部事务（owner/admin 可操作）；平台级用户管理请用「用户管理」页（平台超管）" />
      <Space style={{ marginBottom: 12 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>添加成员</Button>
        <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
      </Space>
      <Table rowKey="id" size="middle" loading={loading} columns={columns} dataSource={rows} pagination={false} />

      <Modal title="添加成员" open={createOpen} onOk={onCreate} onCancel={() => setCreateOpen(false)} okText="创建">
        <Form form={form} layout="vertical">
          <Form.Item name="username" label="用户名" rules={[{ required: true }]}>
            <Input placeholder="3-50 字符" />
          </Form.Item>
          <Form.Item name="email" label="邮箱" rules={[{ required: true, type: 'email' }]}>
            <Input placeholder="name@company.com" />
          </Form.Item>
          <Form.Item name="password" label="初始密码" rules={[{ required: true, min: 6 }]}>
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Form.Item name="tenant_role" label="租户角色" initialValue="viewer">
            <Select options={[
              { value: 'admin', label: 'admin（可管理成员）' },
              { value: 'operator', label: 'operator（可操作任务）' },
              { value: 'viewer', label: 'viewer（只读）' },
            ]} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title={`重置密码：${resetTarget?.username ?? ''}`} open={!!resetTarget}
             onOk={onReset} onCancel={() => setResetTarget(null)} okText="重置">
        <Form form={resetForm} layout="vertical">
          <Form.Item name="new_password" label="新密码" rules={[{ required: true, min: 6 }]}>
            <Input.Password autoComplete="new-password" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default Members
