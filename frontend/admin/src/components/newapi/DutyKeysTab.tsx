/**
 * T-18：值班页内「钥匙」叶。签发≠live。权限未就绪禁用+「权限加载中」，不藏成未授权。
 */
import React, { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Form, Input, Modal, Space, Table, Typography, message } from 'antd'
import { LoadFailure } from '../LoadState'
import { usePermission } from '../../hooks/usePermission'
import { createLitellmKey, listLitellmKeys, type LitellmKeyRow } from '../../services/litellmKeys'
import { apiErrorMessage, isFormValidateError } from '../../utils/errorMessage'

const { Text, Paragraph } = Typography

const LOAD_FAILED = '钥匙列表加载失败。检查网络后重试。'
const ISSUE_LABEL = '签发钥匙'
const READY_HINT = '权限加载中'

export const DutyKeysTab: React.FC = () => {
  const { permissionsReady } = usePermission()
  const queryClient = useQueryClient()
  const [form] = Form.useForm()
  const [open, setOpen] = useState(false)
  const [issued, setIssued] = useState<string | null>(null)

  const listQ = useQuery({
    queryKey: ['litellm-keys'],
    queryFn: listLitellmKeys,
    retry: false,
  })

  const issue = useMutation({
    mutationFn: (alias: string) => createLitellmKey(alias),
    onSuccess: (row) => {
      const token = row.token || row.key || null
      setIssued(token)
      setOpen(false)
      form.resetFields()
      void queryClient.invalidateQueries({ queryKey: ['litellm-keys'] })
      message.success('已签发')
    },
    onError: (e) => {
      if (isFormValidateError(e)) return
      message.error(apiErrorMessage(e, '签发失败'))
    },
  })

  const onIssue = async () => {
    const values = await form.validateFields()
    issue.mutate(String(values.key_alias).trim())
  }

  if (listQ.isError) {
    return <LoadFailure title={LOAD_FAILED} onRetry={() => { void listQ.refetch() }} />
  }

  const rows = listQ.data ?? []
  return (
    <div data-testid="duty-keys">
      <Space style={{ marginBottom: 12 }}>
        <Button
          type="primary"
          disabled={!permissionsReady || issue.isPending}
          onClick={() => setOpen(true)}
        >
          {permissionsReady ? ISSUE_LABEL : READY_HINT}
        </Button>
      </Space>
      <Table<LitellmKeyRow>
        rowKey={(r) => r.key_alias || 'key'}
        size="small"
        loading={listQ.isPending}
        dataSource={rows}
        pagination={false}
        locale={{ emptyText: ' ' }}
        columns={[
          { title: '别名', dataIndex: 'key_alias', render: (v: string | null) => v || '—' },
          { title: '预算', dataIndex: 'max_budget', width: 100, render: (v: number | null) => (v == null ? '—' : v) },
        ]}
      />
      <Modal
        title="签发平台网关钥匙"
        open={open}
        okText="签发"
        confirmLoading={issue.isPending}
        onOk={onIssue}
        onCancel={() => setOpen(false)}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="key_alias" label="别名" rules={[{ required: true, message: '请填写别名' }]}>
            <Input maxLength={128} />
          </Form.Item>
        </Form>
      </Modal>
      <Modal
        title="请立即复制钥匙"
        open={Boolean(issued)}
        okText="我已保存，关闭"
        cancelButtonProps={{ style: { display: 'none' } }}
        onOk={() => setIssued(null)}
        onCancel={() => setIssued(null)}
        destroyOnHidden
      >
        <Paragraph type="warning">明文只显示这一次，关闭后无法再查看明文。</Paragraph>
        <Text code copyable data-testid="duty-key-plaintext" style={{ wordBreak: 'break-all' }}>
          {issued}
        </Text>
      </Modal>
    </div>
  )
}

export default DutyKeysTab
