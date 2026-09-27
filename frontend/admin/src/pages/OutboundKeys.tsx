/**
 * 出站拉数钥匙（FR-51 / T-06）：本企业列表 + 签发（明文一次）+ 吊销。
 * GWT-51.2 空态句（信封 message 单源，data=[] 时后端下发冻结句）；
 * GWT-51.1 签发成功本屏一次性展示明文+复制+警示；GWT-51.8 再进页只见前缀+状态；
 * GWT-51.5/51.9 只读无签发/吊销控件 +「请联系企业管理员」（控件隐藏单支，QA-09）；
 * FR-84 族：列表失败=失败句+重试（≠空表）；签发/吊销失败内联、弹窗不关。
 * 产品名纪律（X-KEY）：全部「出站拉数钥匙」；「渠道组令牌」只出现在互斥说明句。
 */
import React, { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, Button, Card, Form, Input, Modal, Space, Table, Tag, Typography, message,
} from 'antd'
import { ReloadOutlined } from '@ant-design/icons'

import TenantSpaceOnly from '../components/TenantSpaceOnly'
import { useAuthStore } from '../store/useAuthStore'
import { apiErrorMessage, isFormValidateError } from '../utils/errorMessage'
import {
  fetchOutboundKeys, issueOutboundKey, revokeOutboundKey,
  type OutboundKeyIssuedRow, type OutboundKeyRow,
} from '../services/outboundKeys'

const { Text, Paragraph } = Typography

const LOAD_FAILED = '出站拉数钥匙加载失败。检查网络后重试。'
const EMPTY_FALLBACK = '还没有出站拉数钥匙。签发后才能从外部系统拉本企业结果。'
const CANNOT_MANAGE_NOTE = '请联系企业管理员'
const OFFLINE_ISSUE = '网络不可用，没有产生钥匙。'
const ISSUE_FAIL_TAIL = '。没有产生钥匙。'
const PLAINTEXT_ONCE_WARN = '明文仅显示一次，请妥善保存。关闭后无法再查看明文。'
const REVOKE_TITLE = '吊销这把出站拉数钥匙？'
const REVOKE_FAILED = '吊销失败。钥匙仍可使用。'
const REVOKE_OK = '已吊销该出站拉数钥匙。'
const MUTEX_NOTE = '本页只管理出站拉数钥匙；渠道组令牌请在「渠道组」页签发，两者不能互用。'

const KEY_STATUS: Record<string, { label: string; color: string }> = {
  active: { label: '已签发', color: 'green' },
  revoked: { label: '已吊销', color: 'red' },
}

const keyStatusTag = (s: string) => {
  const meta = KEY_STATUS[s] || { label: s, color: 'default' }
  return <Tag color={meta.color}>{meta.label}</Tag>
}

const formatTime = (v: string | null) =>
  (v ? new Date(v).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '—')

const OutboundKeys: React.FC = () => {
  const user = useAuthStore((s) => s.user)
  // 超管无企业空间 → 「属于企业空间」说明态，不发空表请求（同 Usage/渠道组同形）
  const noTenantSpace = Boolean(user?.is_platform_admin) && user?.tenant_id == null
  // 写权与后端 outbound_key_service._ISSUER_ROLES 同口径（owner/admin/operator；viewer 只读）
  const canManage = ['owner', 'admin', 'operator'].includes(String(user?.tenant_role || ''))

  const queryClient = useQueryClient()
  // react-query 托管读模型：刷新保留旧数据，失败可重试（失败 ≠ 空表）
  const keysQuery = useQuery({
    queryKey: ['outbound-keys'],
    queryFn: fetchOutboundKeys,
    enabled: !noTenantSpace,
  })
  const keys = keysQuery.data?.keys ?? []
  const emptySentence = keysQuery.data?.message || EMPTY_FALLBACK

  const [issueOpen, setIssueOpen] = useState(false)
  const [issueError, setIssueError] = useState<string | null>(null)
  const [issued, setIssued] = useState<OutboundKeyIssuedRow | null>(null)
  const [revokeTarget, setRevokeTarget] = useState<OutboundKeyRow | null>(null)
  const [revokeError, setRevokeError] = useState<string | null>(null)
  const [form] = Form.useForm()

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['outbound-keys'] })
  const openIssue = () => { setIssueError(null); setIssueOpen(true) }

  const issueMutation = useMutation({
    mutationFn: issueOutboundKey,
    onSuccess: (row) => {
      // GWT-51.1：明文只在本结果弹窗显示一次；GWT-51.8：列表侧永远只有前缀+状态
      setIssued(row)
      setIssueOpen(false)
      setIssueError(null)
      form.resetFields()
      invalidate()
    },
    onError: (e) => {
      if (isFormValidateError(e)) return
      // 内联可见失败（弹窗不关、无假成功）：「签发失败。{原因或「检查网络后重试」}。没有产生钥匙。」
      setIssueError(`签发失败。${apiErrorMessage(e, '检查网络后重试')}${ISSUE_FAIL_TAIL}`)
    },
  })

  const revokeMutation = useMutation({
    mutationFn: revokeOutboundKey,
    onSuccess: () => {
      message.success(REVOKE_OK)
      setRevokeTarget(null)
      setRevokeError(null)
      invalidate()
    },
    onError: (e) => {
      if (isFormValidateError(e)) return
      // 内联（确认弹窗不关）：钥匙仍可使用
      setRevokeError(REVOKE_FAILED)
    },
  })

  const onIssue = async () => {
    if (typeof navigator !== 'undefined' && !navigator.onLine) {
      setIssueError(OFFLINE_ISSUE) // 离线：弹窗不关、无明文
      return
    }
    let values: { name?: string }
    try { values = await form.validateFields() } catch { return }
    issueMutation.mutate({ name: values.name?.trim() || undefined })
  }

  if (noTenantSpace) return <TenantSpaceOnly what="出站拉数" />

  // FR-84 族：列表失败 = 失败句 + 可点重试；不得画成「暂无数据」空表
  if (keysQuery.isError) {
    return (
      <Alert
        type="error" showIcon title={LOAD_FAILED}
        action={<Button size="small" onClick={() => keysQuery.refetch()}>重试</Button>}
      />
    )
  }

  const loading = keysQuery.isPending

  return (
    <div>
      <Alert type="info" showIcon style={{ marginBottom: 12 }} title={MUTEX_NOTE} />
      {!canManage && (
        <Alert type="info" showIcon style={{ marginBottom: 12 }} title={CANNOT_MANAGE_NOTE} />
      )}
      <Space style={{ marginBottom: 12 }}>
        {canManage ? <Button type="primary" onClick={openIssue}>签发出站拉数钥匙</Button> : null}
        <Button icon={<ReloadOutlined />} loading={keysQuery.isFetching} onClick={() => keysQuery.refetch()}>刷新</Button>
      </Space>

      <Card title="出站拉数钥匙" size="small">
        {keys.length === 0 && !loading ? (
          <Alert
            type="info" showIcon title={emptySentence}
            action={canManage
              ? <Button size="small" type="primary" onClick={openIssue}>签发出站拉数钥匙</Button>
              : undefined}
          />
        ) : (
          <Table rowKey="id" size="middle" loading={loading} dataSource={keys}
                 pagination={{ pageSize: 20, hideOnSinglePage: true }}
                 columns={[
                   { title: '名称', dataIndex: 'name', ellipsis: true, render: (v: string | null) => v || '—' },
                   { title: '前缀', dataIndex: 'key_prefix', width: 160, render: (v: string) => <Text code>{v}…</Text> },
                   { title: '状态', dataIndex: 'status', width: 100, render: keyStatusTag },
                   { title: '签发时间', dataIndex: 'created_at', width: 200, render: (v: string) => formatTime(v) },
                   ...(canManage ? [{
                     title: '操作', width: 90,
                     render: (_: unknown, r: OutboundKeyRow) => (
                       r.status === 'active' ? (
                         <Button size="small" danger
                                 loading={revokeMutation.isPending && revokeMutation.variables === r.id}
                                 onClick={() => { setRevokeTarget(r); setRevokeError(null) }}>吊销</Button>
                       ) : null
                     ),
                   }] : []),
                 ]} />
        )}
      </Card>

      <Modal title="签发出站拉数钥匙" open={issueOpen} okText="签发" confirmLoading={issueMutation.isPending}
             onOk={onIssue} onCancel={() => setIssueOpen(false)} destroyOnHidden>
        {issueError && <Alert type="error" showIcon style={{ marginBottom: 12 }} title={issueError} />}
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="备注名（可选）" rules={[{ max: 64, message: '备注名最多 64 字' }]}>
            <Input placeholder="例如：bi-nightly" maxLength={64} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title="请立即复制出站拉数钥匙" open={Boolean(issued)} okText="我已保存，关闭"
             cancelButtonProps={{ style: { display: 'none' } }} destroyOnHidden
             onOk={() => setIssued(null)} onCancel={() => setIssued(null)}>
        <Paragraph type="warning">{PLAINTEXT_ONCE_WARN}</Paragraph>
        <Paragraph>
          <Text
            code copyable={{
              onCopy: () => message.success('已复制出站拉数钥匙'),
            }} style={{ wordBreak: 'break-all' }} data-testid="issued-plaintext"
          >
            {issued?.plaintext_key}
          </Text>
        </Paragraph>
      </Modal>

      <Modal title={REVOKE_TITLE} open={Boolean(revokeTarget)} okText="确认吊销"
             okButtonProps={{ danger: true }} confirmLoading={revokeMutation.isPending} destroyOnHidden
             onOk={() => revokeTarget && revokeMutation.mutate(revokeTarget.id)}
             onCancel={() => { setRevokeTarget(null); setRevokeError(null) }}>
        {revokeError && <Alert type="error" showIcon style={{ marginBottom: 12 }} title={revokeError} />}
        <Paragraph>
          吊销 <Text code>{revokeTarget?.key_prefix}…</Text> 后不可恢复，外部系统将无法再用它拉取本企业结果。
        </Paragraph>
      </Modal>
    </div>
  )
}

export default OutboundKeys
