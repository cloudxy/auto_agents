import React, { useCallback, useEffect, useState } from 'react'
import { Alert, Button, Empty, Form, Input, Modal, Select, Space, Table, Typography, message } from 'antd'

import { listSources, registerSource, syncSource, type SourceRow } from '../../services/capabilities'
import { usePermission } from '../../hooks/usePermission'
import { apiErrorMessage } from '../../utils/errorMessage'
import { REGISTER_SOURCE, SOURCE_EMPTY, loadFail } from './marketCopy'

const { Text } = Typography

const KIND_OPTIONS = [
  { value: 'local', label: '本地' },
  { value: 'git', label: 'Git' },
  { value: 'url', label: '网址（未支持）' },
]

const SourceTab: React.FC = () => {
  const { isPlatformAdmin } = usePermission()
  const [rows, setRows] = useState<SourceRow[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [form] = Form.useForm()

  const load = useCallback(async () => {
    if (!isPlatformAdmin) {
      setRows([])
      return
    }
    setLoading(true)
    setError(null)
    try {
      const data = await listSources()
      setRows(data.items || [])
    } catch (e) {
      setRows([])
      setError(apiErrorMessage(e, loadFail('源')))
    } finally {
      setLoading(false)
    }
  }, [isPlatformAdmin])

  useEffect(() => { load() }, [load])

  const onRegister = async () => {
    const values = await form.validateFields()
    setBusy(true)
    try {
      await registerSource(values)
      setOpen(false)
      form.resetFields()
      await load()
    } catch (e) {
      message.error(apiErrorMessage(e, '登记失败'))
    } finally {
      setBusy(false)
    }
  }

  const onSync = async (name: string) => {
    setBusy(true)
    try {
      const data = await syncSource(name)
      message.success(`成功 ${data.succeeded} / 失败 ${data.failed}`)
      await load()
    } catch (e) {
      message.error(apiErrorMessage(e, '同步失败'))
    } finally {
      setBusy(false)
    }
  }

  const empty = !loading && !error && rows.length === 0

  return (
    <div>
      {error ? (
        <Alert type="error" showIcon title={error} action={<Button onClick={load}>重试</Button>} />
      ) : null}
      <Space style={{ marginBottom: 12 }} wrap>
        {isPlatformAdmin ? (
          <Button type="primary" onClick={() => setOpen(true)}>{REGISTER_SOURCE}</Button>
        ) : null}
        <Button onClick={load}>刷新</Button>
      </Space>
      {empty ? <Empty description={SOURCE_EMPTY} /> : (
        <Table rowKey="id" size="middle" loading={loading} dataSource={rows} pagination={false}
               columns={[
                 { title: '名称', dataIndex: 'name', render: (v: string) => <Text code>{v}</Text> },
                 { title: '类型', dataIndex: 'source_kind' },
                 { title: '成功', dataIndex: 'last_succeeded' },
                 { title: '失败', dataIndex: 'last_failed' },
                 { title: '错误', dataIndex: 'last_error', render: (v: string | null) => v || '—' },
                 { title: '动作', render: (_: unknown, r: SourceRow) => (
                   isPlatformAdmin ? (
                     <Button size="small" disabled={busy} onClick={() => onSync(r.name)}>同步</Button>
                   ) : null
                 )},
               ]}
        />
      )}
      <Modal title={REGISTER_SOURCE} open={open} onOk={onRegister} onCancel={() => setOpen(false)}
             confirmLoading={busy} destroyOnHidden>
        <Form form={form} layout="vertical" initialValues={{ source_kind: 'local' }}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="source_kind" label="类型" rules={[{ required: true }]}>
            <Select options={KIND_OPTIONS} />
          </Form.Item>
          <Form.Item name="uri" label="路径" rules={[{ required: true }]}><Input /></Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default SourceTab
