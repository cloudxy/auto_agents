/**
 * 渠道组令牌（FR-60 / T-10）：组 + 令牌 + Base URL 三步用法 + 用量。
 * GWT-60.1 签发明文一次 + 同屏 Base URL/三步；60.2 用量只读可见；
 * 60.4 无令牌空态句（走信封 message，单一来源在 relay_service）；
 * 60.7 经办能看不能签（藏控件 + 找管理员句，不是空表）；
 * 60.11 再进页只见前缀与状态。失败句走 FR-84 族（GWT-84.1：失败 ≠ 空表）。
 * 产品名「渠道组令牌」；v2 GWT-70.4「无我的中转令牌」不得进本页。
 */
import React, { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, Button, Card, Form, Input, InputNumber, Modal, Select, Space, Table, Tag, Tooltip, Typography, message,
} from 'antd'
import { ReloadOutlined } from '@ant-design/icons'

import RelayUsage from '../components/relay/RelayUsage'
import TenantSpaceOnly from '../components/TenantSpaceOnly'
import { useAuthStore } from '../store/useAuthStore'
import { apiErrorMessage, isFormValidateError } from '../utils/errorMessage'
import {
  createRelayGroup, fetchRelayPage, issueRelayToken, patchRelayGroup, revokeRelayToken,
  type RelayGroupRow, type RelayTokenRow,
} from '../services/relay'

const { Text, Paragraph } = Typography

const LOAD_FAILED = '渠道组加载失败。检查网络后重试。'
const OFFLINE_ISSUE = '网络不可用，没有产生令牌。'
const EMPTY_GROUPS = '还没有渠道组。创建后才能签发令牌。'
const CANNOT_ISSUE = '当前账号不能签发，请联系企业管理员'
const PLAINTEXT_ONCE_WARN = '明文只显示这一次，关闭后无法再查看明文。'

const GROUP_STATUS: Record<string, string> = { enabled: '启用', disabled: '停用' }
const TOKEN_STATUS: Record<string, { label: string; color: string }> = {
  active: { label: '已签发', color: 'green' },
  revoked: { label: '已吊销', color: 'red' },
  expired: { label: '已过期', color: 'default' },
}

const tokenStatusTag = (s: string) => {
  const meta = TOKEN_STATUS[s] || { label: s, color: 'default' }
  return <Tag color={meta.color}>{meta.label}</Tag>
}

const RelayGroups: React.FC = () => {
  const user = useAuthStore((s) => s.user)
  // GWT-82.4：平台超管无企业空间 → 「属于企业空间」说明态，不发空表请求
  const noTenantSpace = Boolean(user?.is_platform_admin) && user?.tenant_id == null
  // 写权与后端 relay_service._ISSUER_ROLES 同口径（租户角色 owner/admin）
  const canIssue = user?.tenant_role === 'owner' || user?.tenant_role === 'admin'

  const queryClient = useQueryClient()
  // react-query 托管读模型：刷新保留旧数据（用量数字不闪 0），失败可重试
  const pageQuery = useQuery({
    queryKey: ['relay-page'],
    queryFn: fetchRelayPage,
    enabled: !noTenantSpace,
  })
  const groups = pageQuery.data?.groups ?? []
  const tokens = pageQuery.data?.tokens ?? []
  const cannotIssueNote = !canIssue
    ? (pageQuery.data?.groupsMessage || CANNOT_ISSUE)
    : ''

  const [groupOpen, setGroupOpen] = useState(false)
  const [tokenOpen, setTokenOpen] = useState(false)
  const [issueError, setIssueError] = useState<string | null>(null)
  const [issued, setIssued] = useState<RelayTokenRow | null>(null)
  const [form] = Form.useForm()
  const [tokenForm] = Form.useForm()

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['relay-page'] })
  const openIssue = () => { setIssueError(null); setTokenOpen(true) }

  const createMutation = useMutation({
    mutationFn: createRelayGroup,
    onSuccess: () => { message.success('渠道组已创建'); setGroupOpen(false); form.resetFields(); invalidate() },
    onError: (e) => { if (!isFormValidateError(e)) message.error(apiErrorMessage(e, '创建失败')) },
  })

  const issueMutation = useMutation({
    mutationFn: issueRelayToken,
    onSuccess: (row) => {
      // GWT-60.1：明文只在本弹窗显示一次；GWT-60.11：列表侧永远只有前缀+状态
      setIssued(row)
      setTokenOpen(false)
      setIssueError(null)
      tokenForm.resetFields()
      invalidate()
    },
    onError: (e) => {
      if (isFormValidateError(e)) return
      // 内联可见失败（60.5 族：网关不可达句由信封 message 下发），弹窗不关、无假成功
      setIssueError(apiErrorMessage(e, '签发失败'))
    },
  })

  const revokeMutation = useMutation({
    mutationFn: revokeRelayToken,
    onSuccess: () => { message.success('已吊销该渠道组令牌。'); invalidate() },
    onError: (e) => { if (!isFormValidateError(e)) message.error(apiErrorMessage(e, '吊销失败')) },
  })

  const patchMutation = useMutation({
    mutationFn: (r: RelayGroupRow) => patchRelayGroup(r.id, { status: r.status === 'enabled' ? 'disabled' : 'enabled' }),
    onSuccess: () => invalidate(),
    onError: (e) => { if (!isFormValidateError(e)) message.error(apiErrorMessage(e, '操作失败')) },
  })

  const onCreate = async () => {
    let values: { name?: string; rpm_limit?: number; tpm_limit?: number; models?: string }
    try { values = await form.validateFields() } catch { return }
    const models = String(values.models || '')
      .split(/[,，\s]+/).map((s) => s.trim()).filter(Boolean)
    createMutation.mutate({
      name: values.name || '',
      rpm_limit: values.rpm_limit || 0,
      tpm_limit: values.tpm_limit || 0,
      models,
    })
  }

  const onIssue = async () => {
    if (typeof navigator !== 'undefined' && !navigator.onLine) {
      setIssueError(OFFLINE_ISSUE) // 离线：弹窗不关、无明文
      return
    }
    let values: { group_id?: number; name?: string; quota_tokens?: number }
    try { values = await tokenForm.validateFields() } catch { return }
    issueMutation.mutate({
      group_id: values.group_id ?? groups[0]?.id ?? 0,
      name: values.name || '',
      quota_tokens: values.quota_tokens ?? -1,
    })
  }

  if (noTenantSpace) return <TenantSpaceOnly what="渠道组" />

  // GWT-84.1：列表失败 = 失败句 + 可点重试；不得画成「暂无数据」空表
  if (pageQuery.isError) {
    return (
      <Alert
        type="error" showIcon title={LOAD_FAILED}
        action={<Button size="small" onClick={() => pageQuery.refetch()}>重试</Button>}
      />
    )
  }

  const loading = pageQuery.isPending
  const emptyTokensSentence = pageQuery.data?.tokensMessage || '还没有令牌。签发后才能按下方用法调用平台网关。'

  return (
    <div>
      <Alert
        type="info" showIcon style={{ marginBottom: 12 }}
        title="平台渠道窗口与熔断由平台值班维护。本页只管理本企业令牌。"
      />
      {cannotIssueNote && (
        <Alert type="info" showIcon style={{ marginBottom: 12 }} title={cannotIssueNote} />
      )}
      <Space style={{ marginBottom: 12 }}>
        {canIssue ? <Button type="primary" onClick={() => setGroupOpen(true)}>新建渠道组</Button> : null}
        {canIssue ? <Button onClick={openIssue}>签发令牌</Button> : null}
        <Button icon={<ReloadOutlined />} loading={pageQuery.isFetching} onClick={() => pageQuery.refetch()}>刷新</Button>
      </Space>

      <Card title="渠道组" size="small" style={{ marginBottom: 16 }}>
        {groups.length === 0 && !loading ? (
          <Alert
            type="info" showIcon title={EMPTY_GROUPS}
            action={canIssue
              ? <Button size="small" type="primary" onClick={() => setGroupOpen(true)}>创建渠道组</Button>
              : undefined}
          />
        ) : (
          <Table rowKey="id" size="middle" loading={loading} dataSource={groups}
                 pagination={{ pageSize: 20, hideOnSinglePage: true }}
                 columns={[
                   { title: '组名', dataIndex: 'name', ellipsis: true },
                   { title: 'RPM', dataIndex: 'rpm_limit', width: 100, render: (v: number) => (v ? v : '不限') },
                   { title: 'TPM', dataIndex: 'tpm_limit', width: 100, render: (v: number) => (v ? v : '不限') },
                   { title: '模型', dataIndex: 'models', ellipsis: true, render: (v: string[]) => (v?.length ? v.join(', ') : '未限制') },
                   { title: '状态', dataIndex: 'status', width: 90, render: (v: string) => <Tag>{GROUP_STATUS[v] || v}</Tag> },
                   ...(canIssue ? [{
                     title: '操作', width: 90,
                     render: (_: unknown, r: RelayGroupRow) => (
                       <Button size="small" loading={patchMutation.isPending && patchMutation.variables?.id === r.id}
                               onClick={() => patchMutation.mutate(r)}>
                         {r.status === 'enabled' ? '停用' : '启用'}
                       </Button>
                     ),
                   }] : []),
                 ]} />
        )}
      </Card>

      <Card title="令牌（渠道组令牌）" size="small" style={{ marginBottom: 16 }}>
        {tokens.length === 0 && !loading ? (
          <Alert
            type="info" showIcon title={emptyTokensSentence}
            action={canIssue
              ? <Button size="small" type="primary" onClick={openIssue}>签发令牌</Button>
              : undefined}
          />
        ) : (
          <Table rowKey="id" size="middle" loading={loading} dataSource={tokens}
                 pagination={{ pageSize: 20, hideOnSinglePage: true }}
                 columns={[
                   { title: '名称', dataIndex: 'name', ellipsis: true },
                   { title: '前缀', dataIndex: 'key_prefix', width: 160, render: (v: string) => <Text code>{v}…</Text> },
                   { title: '额度', dataIndex: 'quota_tokens', width: 110, render: (v: number) => (v < 0 ? '不限' : v.toLocaleString()) },
                   {
                     title: '累计用量（tokens）', dataIndex: 'used_tokens', width: 170,
                     render: (v: number | null) => v == null
                       ? <Tooltip title="用量暂不可用"><Text type="secondary">—</Text></Tooltip>
                       : v.toLocaleString(),
                   },
                   { title: '状态', dataIndex: 'status', width: 100, render: tokenStatusTag },
                   ...(canIssue ? [{
                     title: '操作', width: 90,
                     render: (_: unknown, r: RelayTokenRow) => (
                       r.status === 'active' ? (
                         <Button size="small" danger
                                 loading={revokeMutation.isPending && revokeMutation.variables === r.id}
                                 onClick={() => revokeMutation.mutate(r.id)}>吊销</Button>
                       ) : null
                     ),
                   }] : []),
                 ]} />
        )}
      </Card>

      {/* 用法区：空态仍渲染（有权者签发后立刻用；无权者也能看用法） */}
      <Card title="调用平台网关（用法）" size="small">
        <RelayUsage />
      </Card>

      <Modal title="新建渠道组" open={groupOpen} okText="创建" confirmLoading={createMutation.isPending}
             onOk={onCreate} onCancel={() => setGroupOpen(false)} destroyOnHidden>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="组名" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="rpm_limit" label="RPM（0=不限）"><InputNumber min={0} style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="tpm_limit" label="TPM（0=不限）"><InputNumber min={0} style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="models" label="模型名单（逗号分隔，空=不限制）"><Input placeholder="gpt-4o, deepseek-chat" /></Form.Item>
        </Form>
      </Modal>

      <Modal title="签发令牌" open={tokenOpen} okText="签发" confirmLoading={issueMutation.isPending}
             onOk={onIssue} onCancel={() => setTokenOpen(false)} destroyOnHidden>
        {issueError && <Alert type="error" showIcon style={{ marginBottom: 12 }} title={issueError} />}
        <Form form={tokenForm} layout="vertical" initialValues={{ group_id: groups[0]?.id, quota_tokens: -1 }}>
          <Form.Item name="group_id" label="渠道组" rules={[{ required: true }]}>
            <Select options={groups.map((g) => ({ value: g.id, label: g.name }))} />
          </Form.Item>
          <Form.Item name="name" label="备注名" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="quota_tokens" label="额度（-1=不限）"><InputNumber style={{ width: '100%' }} /></Form.Item>
        </Form>
      </Modal>

      <Modal title="请立即复制渠道组令牌" open={Boolean(issued)} okText="我已保存，关闭"
             cancelButtonProps={{ style: { display: 'none' } }} destroyOnHidden
             onOk={() => setIssued(null)} onCancel={() => setIssued(null)}>
        <Paragraph type="warning">{PLAINTEXT_ONCE_WARN}</Paragraph>
        <Paragraph>
          <Text
            code copyable={{
              onCopy: () => message.success('已复制渠道组令牌'),
            }} style={{ wordBreak: 'break-all' }} data-testid="issued-plaintext"
          >
            {issued?.plaintext_key}
          </Text>
        </Paragraph>
        {/* GWT-60.1：同一屏给出 Base URL 与三步用法 */}
        <RelayUsage />
      </Modal>
    </div>
  )
}

export default RelayGroups
