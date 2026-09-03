/**
 * 能力中心页（P6 C9）：四类资产统一管理——技能/插件/专家/专家团
 * 技能 Tab 复用 Skills 组件（按钮级权限由 Skills 内部 usePermission 决定）；插件含验证按钮；专家/专家团为定义管理。
 */
import React, { useCallback, useEffect, useState } from 'react'
import {
  Button, Empty, Form, Input, message, Modal, Select, Space,
  Table, Tabs, Tag, Typography,
} from 'antd'
import { ReloadOutlined, SafetyCertificateOutlined } from '@ant-design/icons'

import Skills from './Skills'
import {
  createTeam, listAssets, scanExperts, scanPlugins, verifyPlugin, type AssetRow,
} from '../services/capabilities'
import { apiErrorMessage } from '../utils/errorMessage'

const { Text } = Typography


const STATUS_COLORS: Record<string, string> = {
  experimental: 'default', testing: 'processing', stable: 'success',
  recommended: 'gold', deprecated: 'warning', blacklist: 'error',
}

const Capabilities: React.FC = () => {
  const [tab, setTab] = useState('skills')

  return (
    <div>
      <Tabs activeKey={tab} onChange={setTab} items={[
        { key: 'skills', label: '技能', children: <Skills /> },
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
      await scanPlugins()
      message.success('插件扫描完成')
      load()
    } catch (e) { message.error(apiErrorMessage(e, '扫描失败')) }
  }

  const verify = async (name: string) => {
    try {
      setVerifying(name)
      const result = await verifyPlugin(name)
      const serverResults = Object.entries(result.detail || {})
        .map(([srv, r]) => `${srv}: ${r.health}`).join('; ')
      message.info(`验证 ${name}: ${result.health}${serverResults ? ` (${serverResults})` : ''}`)
      load()
    } catch (e) {
      message.error(apiErrorMessage(e, '验证失败'))
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
      await scanExperts()
      message.success('专家扫描完成')
      load()
    } catch (e) { message.error(apiErrorMessage(e, '扫描失败')) }
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
      await createTeam(values)
      message.success(`专家团「${values.name}」已创建`)
      setFormOpen(false)
      form.resetFields()
      load()
    } catch (e) {
      message.error(apiErrorMessage(e, '创建失败'))
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
