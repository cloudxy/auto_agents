/**
 * 成员管理页（SaaS S2-2）：租户 owner/admin 自助管理子账号。
 * Users 页归平台超管（页面分叉）——本页是租户视角。
 */
import React, { useCallback, useEffect, useState } from 'react'
import { Card,
  Alert, Button, Form, Input, Modal, Select, Space, Switch,
  Table, Tag, Typography, message,
} from 'antd'
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'

import {
  createMember, listMemberAudit, listMembers, patchMember, resetMemberPassword,
  type MemberAuditRow, type MemberRow,
} from '../services/members'
import { apiErrorMessage } from '../utils/errorMessage'

const { Text } = Typography

const ROLE_COLORS: Record<string, string> = {
  owner: 'gold', admin: 'green', operator: 'blue', viewer: 'default',
}

const Members: React.FC = () => {
  const [rows, setRows] = useState<MemberRow[]>([])
  const [audit, setAudit] = useState<MemberAuditRow[]>([])
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
      message.error(apiErrorMessage(e, '成员加载失败'))
    } finally {
      setLoading(false)
    }
    try { setAudit(await listMemberAudit()) } catch { /* 审计非关键路径 */ }
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
      message.error(apiErrorMessage(e, '操作失败'))
    }
  }

  const onRoleChange = async (row: MemberRow, role: string) => {
    try {
      await patchMember(row.id, { tenant_role: role })
      message.success(`${row.username} → ${role}`)
      load()
    } catch (e) {
      message.error(apiErrorMessage(e, '角色变更失败'))
    }
  }

  const onReset = async () => {
    if (!resetTarget) return
    const values = await resetForm.validateFields()
    await resetMemberPassword(resetTarget.id, values.new_password)
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
      <Card title="成员操作审计（本租户，近 50 条）" style={{ marginTop: 16 }}>
        <Table<MemberAuditRow>
          rowKey="id"
          size="small"
          pagination={{ pageSize: 10 }}
          dataSource={audit}
          columns={[
            { title: '时间', dataIndex: 'created_at', width: 180,
              render: (v: string | null) => (v ? new Date(v).toLocaleString('zh-CN') : '-') },
            { title: '操作人', dataIndex: 'actor_name', width: 120 },
            { title: '动作', dataIndex: 'action', width: 150, render: (v: string) => <Tag>{v}</Tag> },
            { title: '对象', dataIndex: 'target', ellipsis: true },
          ]}
        />
      </Card>
    </div>
  )
}

export default Members
