/**
 * LLM 供应商管理页面 - 供应商 CRUD + 激活 + 连通性测试 + 多模型向导（B-M2-3）
 *
 * 能力：
 * - 列表：协议显示名 / 模型列多 Tag（默认金色 +N）/ 激活 / 供应商级测试 / 编辑 / 删除
 * - 新建向导流：选平台（platform-presets 预填协议与地址）→ 填 Key（无需 Key 预设放宽必填）
 *   → 拉取模型列表（probe；默认只显对话模型，tags 模式可手填兜底）→ 指定默认模型
 *   → 表单内测连通（probe-test 1-token）→ 保存（payload 带 models[]）
 * - 编辑态：模型区只读 + 「管理模型」Drawer（fetch diff 三区 / tier/priority/默认/enabled/
 *   健康 Tag / 行内测试；PUT 全量保存）
 * - api_key 编辑留空 = 不修改（既有契约不变）
 *
 * 权限：写操作仅 admin（menu:llm），operator/viewer 只读提示。
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert, Button, Card, Col, Drawer, Form, Input, InputNumber, Modal,
  Popconfirm, Radio, Row, Select, Space, Spin, Switch, Table, Tag, Tooltip, Typography, message,
} from 'antd'
import {
  PlusOutlined, ReloadOutlined, EditOutlined, DeleteOutlined,
  ThunderboltOutlined, CheckCircleOutlined, CloudDownloadOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  fetchLlmProviders, fetchActiveLlmProvider, createLlmProvider, updateLlmProvider,
  deleteLlmProvider, activateLlmProvider, testLlmProvider,
  getPlatformPresets, probeModels, probeTest,
  getLlmProviderModels, putLlmProviderModels, fetchModelsDiff, testLlmProviderModel,
} from '../services/llm'
import type {
  LlmProvider, LlmProviderPayload, LlmTestResult, PlatformPreset, ProviderModelRow,
} from '../services/llm'
import { usePermission } from '../hooks/usePermission'
import { apiErrorMessage, isFormValidateError } from '../utils/errorMessage'

const { Text } = Typography

const PROTOCOL_NAMES: Record<string, string> = {
  openai_compatible: 'OpenAI 兼容',
  anthropic: 'Anthropic 原生',
  google_gemini: 'Google Gemini',
}

const HEALTH_TAGS: Record<string, { color: string; label: string }> = {
  unknown: { color: 'default', label: '未测' },
  healthy: { color: 'success', label: '健康' },
  degraded: { color: 'warning', label: '降级' },
  down: { color: 'error', label: '不可用' },
}

const LlmProviders: React.FC = () => {
  const { hasPermission } = usePermission()
  const canOperate = hasPermission('menu:llm')
  const canDelete = hasPermission('btn:delete')

  const [rows, setRows] = useState<LlmProvider[]>([])
  const [loading, setLoading] = useState(false)
  const [activeProvider, setActiveProvider] = useState<LlmProvider | null>(null)
  const [activeLoaded, setActiveLoaded] = useState(false)

  // 新建/编辑弹窗（向导流）
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<LlmProvider | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm()

  // 向导流状态
  const [presets, setPresets] = useState<PlatformPreset[]>([])
  const [probing, setProbing] = useState(false)
  const [probedModels, setProbedModels] = useState<string[]>([])
  const [probeSearched, setProbeSearched] = useState(false)
  const [probeTestResult, setProbeTestResult] = useState<{ ok: boolean; latency_ms: number; error: string } | null>(null)
  const [probeTesting, setProbeTesting] = useState(false)

  // 模型管理 Drawer
  const [drawerProvider, setDrawerProvider] = useState<LlmProvider | null>(null)
  const [drawerModels, setDrawerModels] = useState<ProviderModelRow[]>([])
  const [drawerLoading, setDrawerLoading] = useState(false)
  const [drawerSaving, setDrawerSaving] = useState(false)
  const [diff, setDiff] = useState<{ new: string[]; existing: string[]; vanished: string[] } | null>(null)
  const [diffLoading, setDiffLoading] = useState(false)
  const [rowTesting, setRowTesting] = useState<string | null>(null)

  const [activatingId, setActivatingId] = useState<number | null>(null)
  const [testingId, setTestingId] = useState<number | null>(null)
  const [testResults, setTestResults] = useState<Record<number, LlmTestResult>>({})
  // 列表模型计数（模型列多 Tag：默认金色 +N）
  const [modelsMap, setModelsMap] = useState<Record<number, ProviderModelRow[]>>({})

  const loadList = useCallback(async (showSpin = true) => {
    if (showSpin) setLoading(true)
    try {
      const list = await fetchLlmProviders()
      setRows(Array.isArray(list) ? list : [])
    } catch {
      message.error('获取 LLM 供应商列表失败')
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
    if (!canOperate || rows.length === 0) return
    rows.forEach(async (row) => {
      try {
        const models = await getLlmProviderModels(row.id)
        setModelsMap((prev) => ({ ...prev, [row.id]: models }))
      } catch { /* 忽略单行失败 */ }
    })
  }, [rows, canOperate])

  const refreshAll = () => {
    loadList(false)
    loadActive()
  }

  // ---------------- 向导流 ----------------
  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    setProbedModels([])
    setProbeSearched(false)
    setProbeTestResult(null)
    setModalOpen(true)
  }

  const openEdit = (row: LlmProvider) => {
    setEditing(row)
    form.resetFields()
    form.setFieldsValue({
      name: row.name,
      provider_type: row.provider_type || 'openai_compatible',
      base_url: row.base_url,
      api_key: undefined,
      model: row.model,
      temperature: row.temperature ?? undefined,
      timeout: row.timeout ?? undefined,
      max_retries: row.max_retries ?? undefined,
      enabled: row.enabled,
      remark: row.remark || undefined,
    })
    setModalOpen(true)
  }

  const selectedProtocol = Form.useWatch('provider_type', form)
  const selectedBaseUrl = Form.useWatch('base_url', form)
  const apiKeyValue = Form.useWatch('api_key', form)
  const selectedModels: string[] = Form.useWatch('models_field', form) || []
  const defaultModel = Form.useWatch('model', form)
  const requiresKey = useMemo(() => {
    const preset = presets.find((p) => p.protocol === selectedProtocol && p.base_url === selectedBaseUrl)
    return preset ? preset.requires_key : true
  }, [presets, selectedProtocol, selectedBaseUrl])

  const onPlatformChange = (presetName: string) => {
    if (presetName === '__custom__') {
      form.setFieldsValue({ provider_type: 'openai_compatible', base_url: '' })
      return
    }
    const preset = presets.find((p) => p.name === presetName)
    if (preset) {
      form.setFieldsValue({ provider_type: preset.protocol, base_url: preset.base_url || undefined })
    }
  }

  const onProbeModels = async () => {
    try {
      setProbing(true)
      const data = await probeModels({
        provider_type: selectedProtocol || 'openai_compatible',
        base_url: selectedBaseUrl || '',
        api_key: apiKeyValue || '',
      })
      setProbedModels(data.models.map((m) => m.id))
      setProbeSearched(true)
      message.success(`拉到 ${data.models.length} 个模型（对话模型 ${data.chat_only_count} 个）`)
    } catch (error) {
      message.error(apiErrorMessage(error, '拉取模型列表失败（可手填模型名兜底）'))
      setProbeSearched(true)
    } finally {
      setProbing(false)
    }
  }

  const onProbeTest = async () => {
    if (!defaultModel) {
      message.warning('请先选择默认模型')
      return
    }
    try {
      setProbeTesting(true)
      const res = await probeTest({
        provider_type: selectedProtocol || 'openai_compatible',
        base_url: selectedBaseUrl || '',
        api_key: apiKeyValue || '',
        model: defaultModel,
      })
      setProbeTestResult(res)
      res.ok ? message.success(`连通正常（${res.latency_ms}ms）`) : message.error(`连通失败：${res.error}`)
    } catch (error) {
      message.error(apiErrorMessage(error, '连通测试请求异常'))
    } finally {
      setProbeTesting(false)
    }
  }

  const onSubmit = async () => {
    try {
      const values = await form.validateFields()
      setSubmitting(true)
      const payload: LlmProviderPayload = {
        name: values.name.trim(),
        provider_type: values.provider_type?.trim() || 'openai_compatible',
        base_url: values.base_url.trim(),
        api_key: values.api_key?.trim() || undefined,
        model: values.model.trim(),
        temperature: values.temperature ?? undefined,
        timeout: values.timeout ?? undefined,
        max_retries: values.max_retries ?? undefined,
        enabled: values.enabled ?? true,
        remark: values.remark?.trim() || undefined,
      }
      if (editing) {
        await updateLlmProvider(editing.id, payload)
        message.success(`供应商「${payload.name}」已更新`)
      } else {
        // 向导流：勾选模型一并落子表（默认模型行 is_default）
        payload.models = (values.models_field || []).map((id: string) => ({
          model_id: id,
          is_default: id === values.model,
        }))
        await createLlmProvider(payload)
        message.success(`供应商「${payload.name}」已创建`)
      }
      setModalOpen(false)
      refreshAll()
    } catch (error) {
      if (isFormValidateError(error)) return
      message.error(apiErrorMessage(error, editing ? '更新供应商失败' : '创建供应商失败'))
    } finally {
      setSubmitting(false)
    }
  }

  // ---------------- 模型管理 Drawer ----------------
  const openDrawer = async (row: LlmProvider) => {
    setDrawerProvider(row)
    setDiff(null)
    setDrawerLoading(true)
    try {
      setDrawerModels(await getLlmProviderModels(row.id))
    } catch (error) {
      message.error(apiErrorMessage(error, '模型列表加载失败'))
    } finally {
      setDrawerLoading(false)
    }
  }

  const onFetchDiff = async () => {
    if (!drawerProvider) return
    try {
      setDiffLoading(true)
      setDiff(await fetchModelsDiff(drawerProvider.id))
    } catch (error) {
      message.error(apiErrorMessage(error, '重新拉取失败'))
    } finally {
      setDiffLoading(false)
    }
  }

  const importNewModels = () => {
    if (!diff) return
    setDrawerModels((prev) => [
      ...prev,
      ...diff.new.filter((id) => !prev.some((m) => m.model_id === id)).map((model_id) => ({
        model_id, alias: '', model_tier: 'basic' as const, priority: 100,
        is_default: false, enabled: true, health_status: 'unknown' as const,
      })),
    ])
    message.success(`已导入 ${diff.new.length} 个新模型（保存后生效）`)
  }

  const patchModel = (modelId: string, patch: Partial<ProviderModelRow>) => {
    setDrawerModels((prev) => prev.map((m) => (m.model_id === modelId ? { ...m, ...patch } : m)))
  }

  const onRowTest = async (modelId: string) => {
    if (!drawerProvider) return
    try {
      setRowTesting(modelId)
      const res = await testLlmProviderModel(drawerProvider.id, modelId)
      patchModel(modelId, { health_status: res.health_status as ProviderModelRow['health_status'], last_latency_ms: res.latency_ms })
      res.ok ? message.success(`${modelId} 连通（${res.latency_ms}ms）`) : message.error(`${modelId}：${res.error}`)
    } catch (error) {
      message.error(apiErrorMessage(error, '测试请求异常'))
    } finally {
      setRowTesting(null)
    }
  }

  const saveDrawer = async () => {
    if (!drawerProvider) return
    const defaults = drawerModels.filter((m) => m.is_default)
    if (defaults.length > 1) {
      message.error('默认模型至多一个')
      return
    }
    try {
      setDrawerSaving(true)
      await putLlmProviderModels(drawerProvider.id, drawerModels.map((m) => ({
        model_id: m.model_id, alias: m.alias, model_tier: m.model_tier,
        priority: m.priority, is_default: m.is_default, enabled: m.enabled,
      })))
      message.success('模型集已保存')
      setDrawerProvider(null)
      refreshAll()
    } catch (error) {
      message.error(apiErrorMessage(error, '保存失败'))
    } finally {
      setDrawerSaving(false)
    }
  }

  // ---------------- 行操作（沿用） ----------------
  const onActivate = async (row: LlmProvider) => {
    try {
      setActivatingId(row.id)
      await activateLlmProvider(row.id)
      message.success(`已激活供应商「${row.name}」`)
      refreshAll()
    } catch (error) {
      message.error(apiErrorMessage(error, '激活失败'))
    } finally {
      setActivatingId(null)
    }
  }

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
      title: '激活', dataIndex: 'is_active', key: 'is_active', width: 100,
      render: (v: boolean) => (v ? <Tag color="gold" icon={<CheckCircleOutlined />}>已激活</Tag> : <Text type="secondary">-</Text>),
    },
    { title: '备注', dataIndex: 'remark', key: 'remark', ellipsis: true, render: (v: string | null) => v || '-' },
    {
      title: '操作', key: 'action', width: 380,
      render: (_: unknown, record: LlmProvider) => {
        const res = testResults[record.id]
        return (
          <Space size={0} wrap>
            {canOperate && (
              <Button type="link" size="small" icon={<CheckCircleOutlined />}
                      disabled={record.is_active} loading={activatingId === record.id}
                      onClick={() => onActivate(record)}>激活</Button>
            )}
            {canOperate && (
              <Button type="link" size="small" icon={<ThunderboltOutlined />}
                      loading={testingId === record.id} onClick={() => onTest(record)}>测试</Button>
            )}
            {canOperate && (
              <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>编辑</Button>
            )}
            {canOperate && (
              <Button type="link" size="small" icon={<CloudDownloadOutlined />}
                      onClick={() => openDrawer(record)}>管理模型</Button>
            )}
            {canDelete && (
              <Popconfirm title="确认删除该供应商？" okText="删除" okButtonProps={{ danger: true }} cancelText="取消"
                          onConfirm={() => onDelete(record)}>
                <Button type="link" danger size="small" icon={<DeleteOutlined />}>删除</Button>
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
              <Space>
                {canOperate && <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建供应商</Button>}
                <Button icon={<ReloadOutlined />} onClick={refreshAll}>刷新</Button>
              </Space>
            }>
        <Table columns={columns} dataSource={rows} rowKey="id" loading={loading}
               pagination={false} scroll={{ x: 1400 }}
               locale={{ emptyText: canOperate ? '暂无 LLM 供应商，点击右上角「新建供应商」添加' : '暂无 LLM 供应商' }} />
      </Card>

      {/* 新建（向导流）/ 编辑弹窗 */}
      <Modal
        title={editing ? `编辑供应商：${editing.name}` : '新建 LLM 供应商（向导）'}
        open={modalOpen} forceRender onOk={onSubmit} onCancel={() => setModalOpen(false)}
        confirmLoading={submitting} okText={editing ? '保存' : '创建'} cancelText="取消" width={620}
      >
        <Form form={form} layout="vertical" initialValues={{ enabled: true }}>
          {!editing && (
            <Form.Item label="选择平台" tooltip="选平台即预填协议与地址（可改）；自定义入口承接任意 OpenAI 兼容端点">
              <Select
                placeholder="OpenAI / Anthropic / Gemini / DeepSeek / Ollama …"
                onChange={onPlatformChange}
                options={[
                  ...presets.map((p) => ({ value: p.name, label: `${p.name}（${PROTOCOL_NAMES[p.protocol]}）` })),
                  { value: '__custom__', label: '自定义（OpenAI 兼容）' },
                ]}
              />
            </Form.Item>
          )}
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入供应商名称' }]}>
            <Input placeholder="如：主用大模型" allowClear />
          </Form.Item>
          <Form.Item name="provider_type" hidden initialValue="openai_compatible"><Input /></Form.Item>
          <Form.Item label="协议">
            <Form.Item name="provider_type" noStyle>
              <Select
                disabled={!!editing}
                options={[
                  { value: 'openai_compatible', label: 'OpenAI 兼容' },
                  { value: 'anthropic', label: 'Anthropic 原生' },
                  { value: 'google_gemini', label: 'Google Gemini' },
                ]}
              />
            </Form.Item>
          </Form.Item>
          <Form.Item
            name="base_url" label="Base URL" validateTrigger="onBlur"
            rules={[
              { required: true, message: '请输入 Base URL' },
              { pattern: /^https?:\/\/\S+/, message: '必须是 http(s) 地址' },
            ]}
          >
            <Input placeholder="https://api.openai.com/v1（选平台后自动预填，可改）" allowClear />
          </Form.Item>
          <Form.Item
            name="api_key" label="API Key"
            tooltip={editing ? '留空表示不修改' : requiresKey ? undefined : '该平台无需 Key（本地推理）'}
            rules={editing || !requiresKey ? [] : [{ required: true, message: '请输入 API Key' }]}
          >
            <Input.Password
              placeholder={editing ? (editing.api_key_masked || '留空表示不修改')
                                    : requiresKey ? 'sk-...' : '（该平台可留空）'}
              autoComplete="new-password"
            />
          </Form.Item>

          {!editing ? (
            <>
              <Form.Item label="模型（拉取后勾选，支持手填兜底）" required>
                <Space.Compact style={{ width: '100%' }}>
                  <Form.Item name="models_field" noStyle initialValue={[]}>
                    <Select
                      mode="tags" placeholder="先拉取列表，或直接手填模型名"
                      style={{ width: '100%' }} allowClear
                      options={probedModels.map((id) => ({ value: id, label: id }))}
                    />
                  </Form.Item>
                  <Button icon={<CloudDownloadOutlined />} loading={probing} onClick={onProbeModels}
                          disabled={!selectedBaseUrl}>
                    拉取模型
                  </Button>
                </Space.Compact>
              </Form.Item>
              <Form.Item
                name="model" label="默认模型（必选一个）"
                rules={[{ required: true, message: '请指定默认模型' }]}
              >
                <Radio.Group>
                  {selectedModels.map((id) => (
                    <Radio key={id} value={id}>{id}</Radio>
                  ))}
                </Radio.Group>
              </Form.Item>
              <Form.Item label="测试连通（保存前用当前表单配置真发 1-token）">
                <Space>
                  <Button icon={<ThunderboltOutlined />} loading={probeTesting} onClick={onProbeTest}
                          disabled={!defaultModel}>
                    测试连通
                  </Button>
                  {probeTestResult && (probeTestResult.ok
                    ? <Tag color="success">{probeTestResult.latency_ms}ms · {defaultModel}</Tag>
                    : <Tag color="error">失败：{probeTestResult.error}</Tag>)}
                </Space>
              </Form.Item>
            </>
          ) : (
            <Form.Item label="模型" tooltip="编辑态模型集经「管理模型」抽屉维护">
              <Space wrap>
                <Tag color="gold">{editing.model || form.getFieldValue('model')}</Tag>
                <Text type="secondary">（列表页「管理模型」增删/改默认）</Text>
              </Space>
            </Form.Item>
          )}

          <Row gutter={16}>
            <Col span={8}><Form.Item name="temperature" label="温度"><InputNumber min={0} max={2} step={0.1} style={{ width: '100%' }} placeholder="0.7" /></Form.Item></Col>
            <Col span={8}><Form.Item name="timeout" label="超时（秒）"><InputNumber min={1} style={{ width: '100%' }} placeholder="60" /></Form.Item></Col>
            <Col span={8}><Form.Item name="max_retries" label="最大重试"><InputNumber min={0} style={{ width: '100%' }} placeholder="2" /></Form.Item></Col>
          </Row>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch checkedChildren="启用" unCheckedChildren="停用" />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} placeholder="用途说明（可选）" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 模型管理 Drawer */}
      <Drawer
        title={`管理模型：${drawerProvider?.name ?? ''}`} width={720} open={!!drawerProvider}
        onClose={() => setDrawerProvider(null)}
        extra={<Space>
          <Button icon={<CloudDownloadOutlined />} loading={diffLoading} onClick={onFetchDiff}>重新拉取 diff</Button>
          <Button type="primary" loading={drawerSaving} onClick={saveDrawer}>保存（全量提交）</Button>
        </Space>}
      >
        {diff && (
          <Alert type="info" showIcon style={{ marginBottom: 12 }}
                 message={
                   <Space wrap>
                     <span>新增 {diff.new.length} / 已有 {diff.existing.length} / 远端已消失 {diff.vanished.length}</span>
                     {diff.new.length > 0 && <Button size="small" onClick={importNewModels}>导入新增</Button>}
                     {diff.vanished.length > 0 && <Text type="warning">建议清理：{diff.vanished.join(', ')}</Text>}
                   </Space>
                 } />
        )}
        {drawerLoading ? <Spin /> : (
          <Table
            rowKey="model_id" size="small" pagination={false}
            dataSource={drawerModels}
            columns={[
              { title: '模型', dataIndex: 'model_id', render: (v: string) => <Text code>{v}</Text> },
              { title: 'Tier', dataIndex: 'model_tier', width: 110, render: (v: string, r: ProviderModelRow) => (
                <Select size="small" value={v} onChange={(tier) => patchModel(r.model_id, { model_tier: tier as 'strong' | 'basic' })}
                        options={[{ value: 'strong', label: 'strong' }, { value: 'basic', label: 'basic' }]} />
              )},
              { title: '优先级', dataIndex: 'priority', width: 100, render: (v: number, r: ProviderModelRow) => (
                <InputNumber size="small" min={0} value={v} onChange={(p) => patchModel(r.model_id, { priority: p ?? 100 })} />
              )},
              { title: '默认', dataIndex: 'is_default', width: 70, render: (v: boolean, r: ProviderModelRow) => (
                <Radio checked={v} onChange={() => setDrawerModels((prev) => prev.map((m) => ({ ...m, is_default: m.model_id === r.model_id })))} />
              )},
              { title: '启用', dataIndex: 'enabled', width: 70, render: (v: boolean, r: ProviderModelRow) => (
                <Switch size="small" checked={v} onChange={(en) => patchModel(r.model_id, { enabled: en })} />
              )},
              { title: '健康', dataIndex: 'health_status', width: 90, render: (v: string, r: ProviderModelRow) => {
                const meta = HEALTH_TAGS[v] || HEALTH_TAGS.unknown
                return <Tag color={meta.color}>{meta.label}{r.last_latency_ms != null ? ` ${r.last_latency_ms}ms` : ''}</Tag>
              }},
              { title: '操作', width: 80, render: (_: unknown, r: ProviderModelRow) => (
                <Button size="small" type="link" loading={rowTesting === r.model_id} onClick={() => onRowTest(r.model_id)}>测试</Button>
              )},
              { title: '', width: 40, render: (_: unknown, r: ProviderModelRow) => (
                <Button size="small" type="link" danger onClick={() => setDrawerModels((prev) => prev.filter((m) => m.model_id !== r.model_id))}>删</Button>
              )},
            ]}
          />
        )}
      </Drawer>
    </>
  )
}

export default LlmProviders
