/**
 * 成员管理页（SaaS S2-2）：租户 owner/admin 自助管理子账号。
 * Users 页归平台超管（页面分叉）——本页是租户视角。
 */
import React, { useCallback, useEffect, useState } from 'react'
import { Card,
  Alert, Button, Form, Input, Modal, Popconfirm, Select, Space, Switch,
  Table, Tag, Typography, message,
} from 'antd'
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'

import {
  createMember, deleteMember, listMemberAudit, listMembers, patchMember, resetMemberPassword, transferOwnership,
  type MemberAuditRow, type MemberRow,
} from '../services/members'
import { apiErrorMessage, isFormValidateError } from '../utils/errorMessage'
import { isNotFoundError } from '../utils/httpError'
import { useAuthStore } from '../store/useAuthStore'
import NotFound from './NotFound'
import { formatDateTime } from '@auto-agents/frontend-shared'
import { tenantRoleLabel } from '../constants/roles'

const { Text } = Typography

/**
 * 创建成员 422 占用文案转可行动提示（F-02）：后端 create_member 的同名/同邮箱
 * 唯一性检查含软删行（username/email"永久占用"口径——删除不可恢复、不可复用，
 * 见 member_service.create_member 注释），裸文案「成员名已存在: x」不解释占用
 * 来源与可行动作；此处按后端 message 前缀映射为带行动建议的文案，其余透传。
 */
const memberConflictMessage = (e: unknown, fallback: string): string => {
  const raw = apiErrorMessage(e, '')
  if (raw.startsWith('成员名已存在')) {
    return '该用户名已被占用（若同名成员已删除：删除不可恢复、用户名不可复用），请更换用户名'
  }
  if (raw.startsWith('邮箱已注册')) {
    return '该邮箱已被占用（若同邮箱成员已删除：删除不可恢复、邮箱不可复用），请更换邮箱'
  }
  return raw || fallback
}

const ROLE_COLORS: Record<string, string> = {
  owner: 'gold', admin: 'green', operator: 'blue', viewer: 'default',
}

/** FR-89 成员写守卫：owner/admin 可操作（页头注释同口径）；只读/经办不渲染写控件（后端 403 为最终防线，RelayGroups/FileTab 同款写法） */
const MEMBER_WRITER_ROLES = ['owner', 'admin']

const Members: React.FC = () => {
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const isOwner = user?.tenant_role === 'owner'
  const canManageMembers = MEMBER_WRITER_ROLES.includes(user?.tenant_role || '')
  const [rows, setRows] = useState<MemberRow[]>([])
  const [audit, setAudit] = useState<MemberAuditRow[]>([])
  const [loading, setLoading] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [form] = Form.useForm()
  const [resetTarget, setResetTarget] = useState<MemberRow | null>(null)
  const [resetForm] = Form.useForm()
  const [transferTarget, setTransferTarget] = useState<MemberRow | null>(null)
  const [transferring, setTransferring] = useState(false)
  const [transferForm] = Form.useForm()
  const [notFound, setNotFound] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setRows(await listMembers())
      setNotFound(false)
    } catch (e) {
      if (isNotFoundError(e)) {
        setNotFound(true)
        setRows([])
      } else {
        message.error(apiErrorMessage(e, '成员加载失败'))
      }
    } finally {
      setLoading(false)
    }
    try { setAudit(await listMemberAudit()) } catch { /* 审计非关键路径 */ }
  }, [])

  useEffect(() => { load() }, [load])

  const onCreate = async () => {
    try {
      const values = await form.validateFields()
      await createMember(values)
      message.success('已添加成员')
      setCreateOpen(false)
      form.resetFields()
      load()
    } catch (e) {
      // F-02：422 占用（同名/同邮箱，含软删占位行）此前静默失败——提示并保留表单
      if (isFormValidateError(e)) return // 表单校验错误已由表单自身展示
      message.error(memberConflictMessage(e, '创建失败'))
    }
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
      message.success('已保存角色')
      load()
    } catch (e) {
      message.error(apiErrorMessage(e, '角色变更失败'))
    }
  }

  const onReset = async () => {
    if (!resetTarget) return
    try {
      const values = await resetForm.validateFields()
      await resetMemberPassword(resetTarget.id, values.new_password)
      message.success(`${resetTarget.username} 密码已重置`)
      setResetTarget(null)
    } catch (e) {
      // F-02 顺带：重置密码此前同型裸奔（失败无反馈）——提示并保留弹窗，可直接重试
      if (isFormValidateError(e)) return
      message.error(apiErrorMessage(e, '密码重置失败'))
    }
  }

  // 决策 D23：转让负责人——本人降为管理员、会话失效，成功后登出重新登录
  const onTransfer = async () => {
    if (!transferTarget) return
    try {
      const values = await transferForm.validateFields()
      setTransferring(true)
      await transferOwnership(transferTarget.id, values.password)
      message.success(`负责人已转让给 ${transferTarget.username}，你已成为管理员，请重新登录`)
      setTransferTarget(null)
      logout()
    } catch (e) {
      if (isFormValidateError(e)) return
      message.error(apiErrorMessage(e, '转让失败'))
    } finally {
      setTransferring(false)
    }
  }

  const onDelete = async (row: MemberRow) => {
    try {
      await deleteMember(row.id)
      message.success('已移除成员')
      load()
    } catch (e) {
      message.error(apiErrorMessage(e, '删除失败'))
    }
  }

  const columns: ColumnsType<MemberRow> = [
    // 定宽：邮箱列 ellipsis 会让表格走固定布局，不定宽的列在窄屏被挤成 0 宽（批次 5）
    { title: '用户名', dataIndex: 'username', width: 140, render: (v: string) => <Text strong>{v}</Text> },
    { title: '邮箱', dataIndex: 'email', width: 220, ellipsis: true },
    {
      title: '租户角色', dataIndex: 'tenant_role', width: 140,
      render: (v: string, row: MemberRow) => (
        row.tenant_role === 'owner' || !canManageMembers
          ? <Tag color={ROLE_COLORS[v]}>{tenantRoleLabel(v)}</Tag>
          : (
            <Select
              size="small" value={v} style={{ width: 110 }}
              onChange={(role) => onRoleChange(row, role)}
              options={['admin', 'operator', 'viewer'].map((r) => ({ value: r, label: tenantRoleLabel(r) }))}
            />
          )
      ),
    },
    {
      title: '状态', dataIndex: 'is_active', width: 100,
      render: (v: boolean, row: MemberRow) => (
        row.tenant_role === 'owner' || !canManageMembers
          ? (v ? <Tag color="success">启用</Tag> : <Tag>停用</Tag>)
          : <Switch size="small" checked={v} onChange={(active) => onToggleActive(row, active)} />
      ),
    },
    {
      title: '操作', width: 240,
      render: (_: unknown, row: MemberRow) => {
        if (row.tenant_role === 'owner') return <Text type="secondary">所有者</Text>
        if (!canManageMembers) return <Text type="secondary">—</Text>
        return (
          <Space size={0}>
            <Button size="small" type="link" onClick={() => { setResetTarget(row); resetForm.resetFields() }}>重置密码</Button>
            {isOwner && row.is_active && (
              <Button size="small" type="link" onClick={() => { setTransferTarget(row); transferForm.resetFields() }}>
                转让负责人
              </Button>
            )}
            <Popconfirm
              title={`删除成员「${row.username}」`}
              description="账号将被移除且不可恢复（登录即时失效），收件箱随之清空；操作审计保留。"
              okText="删除" okButtonProps={{ danger: true }} cancelText="取消"
              onConfirm={() => onDelete(row)}
            >
              <Button size="small" type="link" danger>删除</Button>
            </Popconfirm>
          </Space>
        )
      },
    },
  ]

  if (notFound) return <NotFound />

  return (
    <div>
      <Alert type="info" showIcon style={{ marginBottom: 12 }}
             title="成员管理是企业内部事务，由企业负责人和管理员操作；平台账号请到「用户管理」页（平台超管）" />
      <Space style={{ marginBottom: 12 }}>
        {canManageMembers && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>添加成员</Button>
        )}
        <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
      </Space>
      <Table rowKey="id" size="middle" loading={loading} columns={columns} dataSource={rows} pagination={false} />

      <Modal title="添加成员" open={createOpen} onOk={onCreate} onCancel={() => setCreateOpen(false)} okText="创建">
        <Form form={form} layout="vertical">
          <Form.Item
            name="username"
            label="登录名"
            rules={[
              { required: true, message: '请填写登录名' },
              { max: 256, message: '登录名过长' },
            ]}
          >
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
              { value: 'admin', label: '管理员（可管理成员）' },
              { value: 'operator', label: '操作员（可操作任务）' },
              { value: 'viewer', label: '只读成员' },
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
      <Modal title={`转让负责人给 ${transferTarget?.username ?? ''}`} open={!!transferTarget}
             onOk={onTransfer} onCancel={() => setTransferTarget(null)}
             okText="确认转让" okButtonProps={{ danger: true, loading: transferring }} cancelText="取消">
        <Alert type="warning" showIcon style={{ marginBottom: 16 }}
               title="转让后对方成为企业负责人（套餐、账单、成员管理都归对方），你将降为管理员并需要重新登录；只有新负责人能再转回来。" />
        <Form form={transferForm} layout="vertical">
          <Form.Item name="password" label="你的登录密码" rules={[{ required: true, message: '请输入登录密码确认' }]}>
            <Input.Password autoComplete="current-password" />
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
              render: (v: string | null) => formatDateTime(v) },
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
