/**
 * LLM 供应商管理页（工单 80 拆分后页面壳）
 *
 * 职责：列表加载/激活/供应商级测试/删除 + 平台预设；新建向导与模型集管理在
 * components/llm/{ProviderWizardModal,ModelSetDrawer}。
 */
import React, { useCallback, useEffect, useState } from 'react'
import { Switch, Select,
  Alert, Button, Card, message, Popconfirm, Space, Table, Tag, Tooltip, Typography,
} from 'antd'
import {
  CheckCircleOutlined, CloudDownloadOutlined, EditOutlined, PlusOutlined,
  ReloadOutlined, ThunderboltOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  activateLlmProvider, deactivateLlmProvider, deleteLlmProvider, fetchActiveLlmProvider, fetchLlmProviders,
  getLlmProviderModels, getPlatformPresets, testLlmProvider,
  type LlmProvider, type LlmTestResult, type PlatformPreset, type ProviderModelRow,
} from '../services/llm'
import { usePermission } from '../hooks/usePermission'
import { apiErrorMessage } from '../utils/errorMessage'
import { PROTOCOL_NAMES } from '../components/llm/llmShared'
import ProviderWizardModal from '../components/llm/ProviderWizardModal'
import ModelSetDrawer from '../components/llm/ModelSetDrawer'

const { Text } = Typography

const LlmProviders: React.FC = () => {
  const { hasPermission } = usePermission()
  const canOperate = hasPermission('btn:create')
  const canDelete = hasPermission('btn:delete')

  const [rows, setRows] = useState<LlmProvider[]>([])
  const [loading, setLoading] = useState(false)
  const [activeProvider, setActiveProvider] = useState<LlmProvider | null>(null)
  const [activeLoaded, setActiveLoaded] = useState(false)
  const [presets, setPresets] = useState<PlatformPreset[]>([])
  const [rowTesting, setRowTesting] = useState<string | null>(null)
  const [activatingId, setActivatingId] = useState<number | null>(null)
  const [testingId, setTestingId] = useState<number | null>(null)
  const [testResults, setTestResults] = useState<Record<number, LlmTestResult>>({})
  // 列表模型计数（模型列多 Tag：默认金色 +N）
  const [modelsMap, setModelsMap] = useState<Record<number, ProviderModelRow[]>>({})
  // 向导 / Drawer 由子组件托管，页面只持有开关态
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<LlmProvider | null>(null)
  const [drawerProvider, setDrawerProvider] = useState<LlmProvider | null>(null)
  // 列表筛选（本地过滤：列表量级小无分页）
  const [filterProtocol, setFilterProtocol] = useState<string>('all')
  const [filterEnabled, setFilterEnabled] = useState<string>('all')
  const [filterActive, setFilterActive] = useState<string>('all')

  const loadList = useCallback(async (showSpin = true) => {
    if (showSpin) setLoading(true)
    try {
      setRows(await fetchLlmProviders())
    } catch {
      /* 列表加载失败由壳层兜底 */
    } finally {
      if (showSpin) setLoading(false)
    }
  }, [])

  const loadActive = useCallback(async () => {
    try {
      setActiveProvider(await fetchActiveLlmProvider())
    } catch {
      setActiveProvider(null)
    } finally {
      setActiveLoaded(true)
    }
  }, [])

  useEffect(() => {
    loadList()
    loadActive()
    getPlatformPresets().then(setPresets).catch(() => setPresets([]))
  }, [loadList, loadActive])

  // 列表加载后补各供应商模型集（仅 admin 需要展示模型列计数）
  useEffect(() => {
    rows.forEach(async (row) => {
      try {
        const models = await getLlmProviderModels(row.id)
        setModelsMap((prev) => ({ ...prev, [row.id]: models }))
      } catch { /* 忽略单行失败 */ }
    })
  }, [rows])

  const refreshAll = () => {
    loadList(false)
    loadActive()
  }

  // ---------------- 行操作 ----------------
  const onTest = async (row: LlmProvider) => {
    try {
      setTestingId(row.id)
      const res = await testLlmProvider(row.id)
      setTestResults((prev) => ({ ...prev, [row.id]: res }))
      res.ok ? message.success(`「${row.name}」连通正常（${res.latency_ms ?? '-'}ms）`)
             : message.error(`「${row.name}」连通失败：${res.error || '未知错误'}`)
    } catch (error) {
      const failed: LlmTestResult = { ok: false, latency_ms: null, model: null, error: apiErrorMessage(error, '请求异常') }
      setTestResults((prev) => ({ ...prev, [row.id]: failed }))
      message.error(`「${row.name}」连通失败：${failed.error}`)
    } finally {
      setTestingId(null)
    }
  }

  const onDelete = async (row: LlmProvider) => {
    try {
      await deleteLlmProvider(row.id)
      message.success(`供应商「${row.name}」已删除`)
      refreshAll()
    } catch (error) {
      message.error(apiErrorMessage(error, '删除失败'))
    }
  }

  // ---------------- 表格列 ----------------
  const columns: ColumnsType<LlmProvider> = [
    { title: '名称', dataIndex: 'name', key: 'name', width: 140, render: (v: string) => <Text strong>{v}</Text> },
    {
      title: '协议', dataIndex: 'provider_type', key: 'provider_type', width: 120,
      render: (v: string | null) => <Tag color="blue">{PROTOCOL_NAMES[v || 'openai_compatible'] || v}</Tag>,
    },
    {
      title: 'Base URL', dataIndex: 'base_url', key: 'base_url', width: 200, ellipsis: true,
      render: (v: string) => <Tooltip title={v}><Text code style={{ fontSize: 12 }}>{v}</Text></Tooltip>,
    },
    {
      title: '模型', dataIndex: 'model', key: 'model', width: 220,
      render: (v: string, record: LlmProvider) => {
        const models = modelsMap[record.id] || []
        const extra = models.filter((m) => m.model_id !== v).length
        return (
          <Space size={4} wrap>
            {v && <Tag color="gold" style={{ marginInlineEnd: 0 }}>{v}</Tag>}
            {extra > 0 && <Tag style={{ marginInlineEnd: 0 }}>+{extra}</Tag>}
            {!v && <Text type="secondary">-</Text>}
          </Space>
        )
      },
    },
    { title: '状态', dataIndex: 'enabled', key: 'enabled', width: 80, render: (v: boolean) => (v ? <Tag color="success">启用</Tag> : <Tag>停用</Tag>) },
    {
      title: '激活', dataIndex: 'is_active', key: 'is_active', width: 90,
      render: (v: boolean, record: LlmProvider) => (canOperate ? (
        <Switch
          checked={v} checkedChildren="已激活" unCheckedChildren="未激活"
          loading={activatingId === record.id}
          onChange={async (checked) => {
            try {
              setActivatingId(record.id)
              await (checked ? activateLlmProvider(record.id) : deactivateLlmProvider(record.id))
              message.success(checked ? `已激活「${record.name}」` : `已取消激活「${record.name}」（运行时回退默认配置）`)
              refreshAll()
            } catch (e) { message.error(apiErrorMessage(e, checked ? '激活失败' : '取消激活失败')) }
            finally { setActivatingId(null) }
          }}
        />
      ) : (v ? <Tag color="gold" icon={<CheckCircleOutlined />}>已激活</Tag> : <Text type="secondary">-</Text>)),
    },
    { title: '备注', dataIndex: 'remark', key: 'remark', ellipsis: true, render: (v: string | null) => v || '-' },
    {
      title: '操作', key: 'action', width: 380,
      render: (_: unknown, record: LlmProvider) => {
        const res = testResults[record.id]
        return (
          <Space size={0} wrap>
            {canOperate && (
              <Button type="link" size="small" icon={<ThunderboltOutlined />}
                      loading={testingId === record.id} onClick={() => onTest(record)}>测试</Button>
            )}
            {canOperate && (
              <Button type="link" size="small" icon={<EditOutlined />}
                      onClick={() => { setEditing(record); setModalOpen(true) }}>编辑</Button>
            )}
            {canOperate && (
              <Button type="link" size="small" icon={<CloudDownloadOutlined />}
                      onClick={() => setDrawerProvider(record)}>管理模型</Button>
            )}
            {canDelete && (
              <Popconfirm title="确认删除该供应商？" okText="删除" okButtonProps={{ danger: true }} cancelText="取消"
                          onConfirm={() => onDelete(record)}>
                <Button type="link" danger size="small" icon={<ThunderboltOutlined />}>删除</Button>
              </Popconfirm>
            )}
            {res && (res.ok
              ? <Tag color="success" style={{ marginLeft: 8 }}>{res.latency_ms ?? '-'}ms · {res.model || '-'}</Tag>
              : <Tooltip title={res.error || '未知错误'}><Tag color="error" style={{ marginLeft: 8, cursor: 'help' }}>失败</Tag></Tooltip>)}
          </Space>
        )
      },
    },
  ]

  return (
    <>
      {!canOperate && (
        <Alert type="info" showIcon style={{ marginBottom: 16 }} message="仅管理员可管理供应商"
               description="当前账号为只读视图；新建/激活/测试/编辑/删除操作仅管理员可用。" />
      )}

      {activeLoaded && (activeProvider ? (
        <Alert type="success" showIcon style={{ marginBottom: 16 }}
               message={`当前激活供应商：${activeProvider.name}（${activeProvider.model || '-'}）`} />
      ) : (
        <Alert type="warning" showIcon style={{ marginBottom: 16 }} message="尚未激活任何 LLM 供应商"
               description="AI 采集等功能依赖已激活的 LLM 供应商，请在列表中选择一个并点击「激活」。" />
      ))}

      <Card title="LLM 供应商配置"
            extra={
              <Space wrap>
                <Select size="small" style={{ width: 140 }} value={filterProtocol}
                        onChange={setFilterProtocol}
                        options={[
                          { value: 'all', label: '全部协议' },
                          { value: 'openai_compatible', label: 'OpenAI 兼容' },
                          { value: 'anthropic', label: 'Anthropic' },
                          { value: 'google_gemini', label: 'Gemini' },
                        ]} />
                <Select size="small" style={{ width: 110 }} value={filterEnabled}
                        onChange={setFilterEnabled}
                        options={[
                          { value: 'all', label: '全部状态' },
                          { value: 'enabled', label: '启用' },
                          { value: 'disabled', label: '停用' },
                        ]} />
                <Select size="small" style={{ width: 110 }} value={filterActive}
                        onChange={setFilterActive}
                        options={[
                          { value: 'all', label: '全部激活位' },
                          { value: 'active', label: '已激活' },
                          { value: 'inactive', label: '未激活' },
                        ]} />
                {canOperate && <Button type="primary" icon={<PlusOutlined />}
                                       onClick={() => { setEditing(null); setModalOpen(true) }}>新建供应商</Button>}
                <Button icon={<ReloadOutlined />} onClick={refreshAll}>刷新</Button>
              </Space>
            }>
        <Table columns={columns} dataSource={rows.filter((r) =>
          (filterProtocol === 'all' || (r.provider_type || 'openai_compatible') === filterProtocol) &&
          (filterEnabled === 'all' || (filterEnabled === 'enabled') === r.enabled) &&
          (filterActive === 'all' || (filterActive === 'active') === r.is_active)
        )} rowKey="id" loading={loading}
               pagination={false} scroll={{ x: 1400 }}
               locale={{ emptyText: canOperate ? '暂无 LLM 供应商，点击右上角「新建供应商」添加' : '暂无 LLM 供应商' }} />
      </Card>

      <ProviderWizardModal
        open={modalOpen} editing={editing} presets={presets}
        onClose={() => setModalOpen(false)} onSaved={refreshAll} />
      <ModelSetDrawer
        provider={drawerProvider} onClose={() => setDrawerProvider(null)} onSaved={refreshAll} />
    </>
  )
}

export default LlmProviders
