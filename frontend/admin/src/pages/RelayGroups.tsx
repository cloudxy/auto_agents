/**
 * 我的渠道组（T-20）：SKU none/active/expired；明文一次；租户 /newapi 仍 404。
 * 读 T-18 GET /relay/sku，禁止 COUNT 组行当已买。禁 FR-U24 四字。
 */
import React, { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, Button, Card, Form, Input, InputNumber, Modal, Select, Skeleton, Space, Table, Tag, Tooltip, Typography, message,
} from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'

import RelaySkuEmpty from '../components/relay/RelaySkuEmpty'
import RelayUsage from '../components/relay/RelayUsage'
import { ContactAdminModal } from '../components/quota/ContactAdminModal'
import TenantSpaceOnly from '../components/TenantSpaceOnly'
import {
  RELAY_CANNOT_ISSUE,
  RELAY_COPIED_TOAST,
  RELAY_EMPTY_GROUPS,
  RELAY_ISSUED_TOAST,
  RELAY_LOAD_FAILED,
  RELAY_OFFLINE_ISSUE,
  RELAY_OFFLINE_UPGRADE,
  RELAY_PLAINTEXT_ONCE,
  RELAY_SKU_EXPIRED,
  RELAY_SKU_INACTIVE,
  RELAY_SKU_NONE,
  RELAY_TOKENS_EMPTY,
} from '../constants/relayCopy'
import { listMyOrders } from '../services/billing'
import {
  createRelayGroup, fetchRelayPage, fetchRelaySku, issueRelayToken, patchRelayGroup, revokeRelayToken,
  type RelayGroupRow, type RelayTokenRow,
} from '../services/relay'
import { useAuthStore } from '../store/useAuthStore'
import { apiErrorCode } from '../utils/collectBlock'
import { apiErrorMessage, isFormValidateError } from '../utils/errorMessage'

const { Text, Paragraph } = Typography

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

const isOffline = () => typeof navigator !== 'undefined' && navigator.onLine === false

const RelayGroups: React.FC = () => {
  const user = useAuthStore((s) => s.user)
  const navigate = useNavigate()
  const noTenantSpace = Boolean(user?.is_platform_admin) && user?.tenant_id == null
  const buyer = user?.tenant_role === 'owner' || user?.tenant_role === 'admin'

  const queryClient = useQueryClient()
  const skuQuery = useQuery({
    queryKey: ['relay-sku'],
    queryFn: fetchRelaySku,
    enabled: !noTenantSpace,
    retry: false,
  })
  const sku = skuQuery.data
  const skuActive = sku?.status === 'active'
  const pageQuery = useQuery({
    queryKey: ['relay-page'],
    queryFn: fetchRelayPage,
    enabled: !noTenantSpace && skuActive,
    retry: false,
  })
  const ordersQuery = useQuery({
    queryKey: ['my-orders'],
    queryFn: listMyOrders,
    enabled: !noTenantSpace && skuQuery.isSuccess && !skuActive,
    retry: false,
  })
  const groups = skuActive ? (pageQuery.data?.groups ?? []) : []
  const tokens = skuActive ? (pageQuery.data?.tokens ?? []) : []
  const canIssue = Boolean(skuActive && buyer)
  const cannotIssueNote = skuActive && !canIssue
    ? (pageQuery.data?.groupsMessage || RELAY_CANNOT_ISSUE)
    : ''
  const fulfillmentPending = (ordersQuery.data || []).some(
    (row) => row.product_code === 'relay' && row.status === 'paid_pending_fulfillment',
  )

  const [groupOpen, setGroupOpen] = useState(false)
  const [tokenOpen, setTokenOpen] = useState(false)
  const [contactOpen, setContactOpen] = useState(false)
  const [issueError, setIssueError] = useState<string | null>(null)
  const [issued, setIssued] = useState<RelayTokenRow | null>(null)
  const [form] = Form.useForm()
  const [tokenForm] = Form.useForm()

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['relay-page'] })
    void queryClient.invalidateQueries({ queryKey: ['relay-sku'] })
    void queryClient.invalidateQueries({ queryKey: ['my-orders'] })
  }

  const onUpgrade = () => {
    if (isOffline()) {
      message.warning(RELAY_OFFLINE_UPGRADE)
      return
    }
    const upgrade = sku?.upgrade
    if (upgrade?.action === 'checkout' && upgrade.checkout_path) {
      navigate(upgrade.checkout_path)
      return
    }
    setContactOpen(true)
  }

  const createMutation = useMutation({
    mutationFn: createRelayGroup,
    onSuccess: () => { message.success('渠道组已创建'); setGroupOpen(false); form.resetFields(); invalidate() },
    onError: (e) => { if (!isFormValidateError(e)) message.error(apiErrorMessage(e, '创建失败')) },
  })

  const issueMutation = useMutation({
    mutationFn: issueRelayToken,
    onSuccess: (row) => {
      setIssued(row)
      setTokenOpen(false)
      setIssueError(null)
      tokenForm.resetFields()
      message.success(RELAY_ISSUED_TOAST)
      invalidate()
    },
    onError: (e) => {
      if (isFormValidateError(e)) return
      const code = apiErrorCode(e)
      if (code === RELAY_SKU_INACTIVE) {
        setIssueError(apiErrorMessage(e, sku?.status === 'expired' ? RELAY_SKU_EXPIRED : RELAY_SKU_NONE))
        return
      }
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
    if (isOffline()) {
      setIssueError(RELAY_OFFLINE_ISSUE)
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

  if (skuQuery.isError || (skuActive && pageQuery.isError)) {
    return (
      <Alert
        type="error" showIcon title={RELAY_LOAD_FAILED}
        action={<Button size="small" onClick={() => { void skuQuery.refetch(); void pageQuery.refetch() }}>重试</Button>}
      />
    )
  }

  if (skuQuery.isPending || (skuActive && pageQuery.isPending && !pageQuery.data)) {
    return <Skeleton active paragraph={{ rows: 8 }} />
  }

  if (!skuActive) {
    return (
      <>
        <RelaySkuEmpty
          status={sku?.status || 'none'}
          title={sku?.empty_title}
          hint={sku?.empty_hint}
          fulfillmentPending={fulfillmentPending}
          onUpgrade={onUpgrade}
          onRefresh={() => invalidate()}
        />
        <ContactAdminModal open={contactOpen} onClose={() => setContactOpen(false)} />
      </>
    )
  }

  const loading = pageQuery.isPending
  const openIssue = () => { setIssueError(null); setTokenOpen(true) }

  return (
    <div data-testid="relay-active">
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
            type="info" showIcon title={RELAY_EMPTY_GROUPS}
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
            type="info" showIcon title={RELAY_TOKENS_EMPTY}
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
        <Paragraph type="warning">{RELAY_PLAINTEXT_ONCE}</Paragraph>
        <Paragraph>
          <Text
            code copyable={{
              onCopy: () => message.success(RELAY_COPIED_TOAST),
            }} style={{ wordBreak: 'break-all' }} data-testid="issued-plaintext"
          >
            {issued?.plaintext_key}
          </Text>
        </Paragraph>
        <RelayUsage />
      </Modal>
    </div>
  )
}

export default RelayGroups
