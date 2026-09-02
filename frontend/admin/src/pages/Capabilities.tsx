/**
 * 能力中心页（P6 C9）：四类资产统一管理——技能/插件/专家/专家团
 * 技能 Tab 复用 Skills 组件；插件含验证按钮；专家/专家团为定义管理。
 */
import React, { useCallback, useEffect, useState } from 'react'
import {
  Badge, Button, Card, Empty, Form, Input, message, Modal, Select, Space,
  Table, Tabs, Tag, Typography,
} from 'antd'
import { ReloadOutlined, SafetyCertificateOutlined } from '@ant-design/icons'

import api, { unwrap } from '../services/api'
import Skills from './Skills'

const { Text } = Typography

interface AssetRow {
  id: number
  asset_type: string
  name: string
  title: string
  category: string
  status: string
  tier?: string | null
  score?: number | null
  sync_state: string
}

const STATUS_COLORS: Record<string, string> = {
  experimental: 'default', testing: 'processing', stable: 'success',
  recommended: 'gold', deprecated: 'warning', blacklist: 'error',
}

const listAssets = (type: string): Promise<{ total: number; items: AssetRow[] }> =>
  api.get('/capabilities', { params: { type, page_size: 50 } }).then((r) => unwrap<{ total: number; items: AssetRow[] }>(r))

const Capabilities: React.FC = () => {
  const [tab, setTab] = useState('skills')

  return (
    <div>
      <Tabs activeKey={tab} onChange={setTab} items={[
        { key: 'skills', label: '技能', children: <Skills canEdit canAdmin /> },
        { key: 'plugins', label: '插件', children: <PluginTab /> },
        { key: 'experts', label: '专家', children: <ExpertTab /> },
        { key: 'teams', label: '专家团', children: <TeamTab /> },
      ]} />
    </div>
  )
}

const PluginTab: React.FC = () => {
  const [rows, setRows] = useState<AssetRow[]>([])
  const [loading, setLoading] = useState(false)
  const [verifying, setVerifying] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try { setRows((await listAssets('plugin')).items) } finally { setLoading(false) }
  }, [])
  useEffect(() => { load() }, [load])

  const scan = async () => {
    try {
      await api.post('/capabilities/scan-plugins')
      message.success('插件扫描完成')
      load()
    } catch (e) { message.error(`扫描失败: ${e instanceof Error ? e.message : String(e)}`) }
  }

  const verify = async (name: string) => {
    try {
      setVerifying(name)
      const result = await api.post(`/capabilities/plugins/${encodeURIComponent(name)}/verify`)
        .then((r) => unwrap<{ health: string; detail: Record<string, { health: string; detail: string }> }>(r))
      const serverResults = Object.entries(result.detail || {})
        .map(([srv, r]) => `${srv}: ${r.health}`).join('; ')
      message.info(`验证 ${name}: ${result.health}${serverResults ? ` (${serverResults})` : ''}`)
      load()
    } catch (e) {
      message.error(`验证失败: ${e instanceof Error ? e.message : String(e)}`)
    } finally { setVerifying(null) }
  }

  return (
    <div>
      <Space style={{ marginBottom: 12 }}>
        <Button type="primary" onClick={scan}>扫描插件目录</Button>
        <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
        <Text type="secondary">插件经 MCP 验证后方可分发（ADR-0001）</Text>
      </Space>
      <Table rowKey="id" size="middle" loading={loading} dataSource={rows} pagination={false}
             locale={{ emptyText: <Empty description="暂无插件——在 capability-library/plugins/ 放入后扫描" /> }}
             columns={[
               { title: '名称', dataIndex: 'name', render: (v: string) => <Text code>{v}</Text> },
               { title: '描述', dataIndex: 'title', ellipsis: true },
               { title: '状态', dataIndex: 'status', render: (v: string) => <Tag color={STATUS_COLORS[v]}>{v}</Tag> },
               { title: '操作', render: (_: unknown, r: AssetRow) => (
                 <Button size="small" icon={<SafetyCertificateOutlined />}
                         loading={verifying === r.name}
                         onClick={() => verify(r.name)}>验证</Button>
               )},
             ]} />
    </div>
  )
}

const ExpertTab: React.FC = () => {
  const [rows, setRows] = useState<AssetRow[]>([])
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try { setRows((await listAssets('expert')).items) } finally { setLoading(false) }
  }, [])
  useEffect(() => { load() }, [load])

  const scan = async () => {
    try {
      await api.post('/capabilities/scan-experts')
      message.success('专家扫描完成')
      load()
    } catch (e) { message.error(`扫描失败: ${e instanceof Error ? e.message : String(e)}`) }
  }

  return (
    <div>
      <Space style={{ marginBottom: 12 }}>
        <Button type="primary" onClick={scan}>扫描专家目录</Button>
        <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
      </Space>
      <Table rowKey="id" size="middle" loading={loading} dataSource={rows} pagination={false}
             locale={{ emptyText: <Empty description="暂无专家——在 capability-library/experts/ 放入 AGENT.md 后扫描" /> }}
             columns={[
               { title: '专家', dataIndex: 'name', render: (v: string, r: AssetRow) => <Text strong>{r.title || v}</Text> },
               { title: '状态', dataIndex: 'status', render: (v: string) => <Tag color={STATUS_COLORS[v]}>{v}</Tag> },
               { title: '同步', dataIndex: 'sync_state' },
             ]} />
    </div>
  )
}

const TeamTab: React.FC = () => {
  const [rows, setRows] = useState<AssetRow[]>([])
  const [loading, setLoading] = useState(false)
  const [formOpen, setFormOpen] = useState(false)
  const [form] = Form.useForm()
  const [experts, setExperts] = useState<string[]>([])

  const load = useCallback(async () => {
    setLoading(true)
    try { setRows((await listAssets('expert_team')).items) } finally { setLoading(false) }
  }, [])
  useEffect(() => {
    load()
    listAssets('expert').then((d) => setExperts(d.items.map((i) => i.name))).catch(() => {})
  }, [load])

  const onCreate = async () => {
    const values = await form.validateFields()
    try {
      await api.post('/capabilities/teams', values)
      message.success(`专家团「${values.name}」已创建`)
      setFormOpen(false)
      form.resetFields()
      load()
    } catch (e) {
      message.error(`创建失败: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  return (
    <div>
      <Space style={{ marginBottom: 12 }}>
        <Button type="primary" onClick={() => setFormOpen(true)}>组建专家团</Button>
        <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
        <Text type="secondary">一期为定义层（导出 TEAM.md）；平台内执行引擎二期</Text>
      </Space>
      <Table rowKey="id" size="middle" loading={loading} dataSource={rows} pagination={false}
             locale={{ emptyText: <Empty description="暂无专家团" /> }}
             columns={[
               { title: '专家团', dataIndex: 'name', render: (v: string) => <Text strong>{v}</Text> },
               { title: '状态', dataIndex: 'status', render: (v: string) => <Tag color={STATUS_COLORS[v]}>{v}</Tag> },
               { title: '导出', render: (_: unknown, r: AssetRow) => (
                 <Button size="small" type="link"
                         onClick={() => window.open(`/api/v1/capabilities/teams/${encodeURIComponent(r.name)}/export`, '_blank')}>
                   TEAM.md
                 </Button>
               )},
             ]} />
      <Modal title="组建专家团" open={formOpen} onOk={onCreate} onCancel={() => setFormOpen(false)} okText="创建">
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="团队名" rules={[{ required: true }]}>
            <Input placeholder="如 review-squad" />
          </Form.Item>
          <Form.Item name="leader" label="团长专家" rules={[{ required: true }]}>
            <Select options={experts.map((e) => ({ value: e, label: e }))} />
          </Form.Item>
          <Form.Item name="members" label="成员专家">
            <Select mode="multiple" options={experts.map((e) => ({ value: e, label: e }))} />
          </Form.Item>
          <Form.Item name="workflow_md" label="协作流程">
            <Input.TextArea rows={3} placeholder="团长拆解 → 并行执行 → 汇总交付" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default Capabilities
