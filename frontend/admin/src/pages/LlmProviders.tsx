/**
 * LLM 供应商管理页（工单 80 拆分后页面壳）
 *
 * 职责：列表加载/设默认/供应商级测试/删除 + 平台预设；新建向导与模型集管理在
 * components/llm/{ProviderWizardModal,ModelSetDrawer}。
 *
 * FR-97（T-30）：该页配置「未指定模型时默认用哪一个」——用户可见词只有
 * 「默认 / 设为默认」，不出现「激活」指代该动作；后端 is_active 机制与
 * activate/deactivate 端点不动（内部字段名可留，edge-states §LLM 配置）。
 */
import React, { useCallback, useEffect, useState } from 'react'
import { Alert, Button, message, Modal, Popconfirm, Select,
  Space, Table, Tag, Tooltip, Typography,
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
import { useAuthStore } from '../store/useAuthStore'
import { apiErrorMessage } from '../utils/errorMessage'
import { PROTOCOL_NAMES } from '../components/llm/llmShared'
import ProviderWizardModal from '../components/llm/ProviderWizardModal'
import ModelSetDrawer from '../components/llm/ModelSetDrawer'

const { Text } = Typography

// FR-97 文案（edge-states 钉句；全页用户可见面不得出现「激活」）
const DEFAULT_EXPLAIN = '未指定模型时，默认使用该模型，可按需更换。'
const NO_DEFAULT_HINT = '还没有默认供应商。未指定模型的请求将使用平台公共模型。'
const EMPTY_PROVIDERS = '还没有模型供应商。'
const LIST_LOAD_FAILED = '供应商列表加载失败。检查网络后重试。'
const CANNOT_SET_DEFAULT = '当前账号不能设置默认，请联系企业管理员'
const MODEL_TAG_HINT = '未指定模型时使用'
const OFFLINE_DEFAULT = '网络不可用，默认没有更改。'

const LlmProviders: React.FC = () => {
  const user = useAuthStore((s) => s.user)
  const { hasPermission, isPlatformAdmin } = usePermission()
  const canOperate = hasPermission('btn:create')
  const canDelete = hasPermission('btn:delete')
  const canWriteRow = (row: LlmProvider) =>
    canOperate && (isPlatformAdmin || row.tenant_id !== null)
  // GWT-97.1/97.2 主语=租户负责人/公司管理员（tenant_role owner/admin，
  // 与 relay _ISSUER_ROLES 同口径）；平台超管在平台行沿用既有写面
  const isIssuer = user?.tenant_role === 'owner' || user?.tenant_role === 'admin'
  const canSetDefaultRow = (row: LlmProvider) => canWriteRow(row) && (isPlatformAdmin || isIssuer)

  const [rows, setRows] = useState<LlmProvider[]>([])
  const [loading, setLoading] = useState(false)
  const [listError, setListError] = useState(false)
  const [activeProvider, setActiveProvider] = useState<LlmProvider | null>(null)
  const [activeLoaded, setActiveLoaded] = useState(false)
  const [presets, setPresets] = useState<PlatformPreset[]>([])
  const [settingId, setSettingId] = useState<number | null>(null)
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
  // 「设为默认」确认弹窗（GWT-97.2 切换确认；失败内联、弹窗不关）
  const [defaultTarget, setDefaultTarget] = useState<LlmProvider | null>(null)
  const [setting, setSetting] = useState(false)
  const [setDefaultError, setSetDefaultError] = useState<string | null>(null)

  const loadList = useCallback(async (showSpin = true) => {
    if (showSpin) setLoading(true)
    try {
      setRows(await fetchLlmProviders())
      setListError(false)
    } catch {
      // 失败句不走空态（GWT-97.3）：置错误态，旧行保留（刷新保留行）
      setListError(true)
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
      if (res.ok) {
        message.success('连接成功')
        return
      }
      const reason = res.error || '该行地址无响应'
      const failText = `连接失败：连的是本企业供应商「${row.name}」，不是平台网关。${reason}。检查该行地址与密钥后，再点测试连接。`
      setTestResults((prev) => ({ ...prev, [row.id]: { ...res, error: failText } }))
    } catch (error) {
      const reason = apiErrorMessage(error, '该行地址无响应')
      const failText = `连接失败：连的是本企业供应商「${row.name}」，不是平台网关。${reason}。检查该行地址与密钥后，再点测试连接。`
      const failed: LlmTestResult = { ok: false, latency_ms: null, model: null, error: failText }
      setTestResults((prev) => ({ ...prev, [row.id]: failed }))
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

  const offline = () => typeof navigator !== 'undefined' && !navigator.onLine

  // 设为默认（后端 activate 端点不动）：成功关弹窗刷新；失败/离线内联、弹窗不关
  const applySetDefault = async (row: LlmProvider) => {
    if (offline()) {
      setSetDefaultError(OFFLINE_DEFAULT)
      return
    }
    try {
      setSetting(true)
      await activateLlmProvider(row.id)
      message.success(`已将“${row.name}”设为默认。`)
      setDefaultTarget(null)
      setSetDefaultError(null)
      refreshAll()
    } catch (e) {
      setSetDefaultError(`设置默认失败。${apiErrorMessage(e, '检查网络后重试')}。原默认保持不变。`)
    } finally {
      setSetting(false)
    }
  }

  const onCancelDefault = async (row: LlmProvider) => {
    if (offline()) {
      message.error(OFFLINE_DEFAULT)
      return
    }
    try {
      setSettingId(row.id)
      await deactivateLlmProvider(row.id)
      message.success(`已取消“${row.name}”的默认。未指定模型的请求将使用平台公共模型。`)
      refreshAll()
    } catch (e) {
      message.error(apiErrorMessage(e, '取消默认失败'))
    } finally {
      setSettingId(null)
    }
  }

  // ---------------- 表格列 ----------------
  const columns: ColumnsType<LlmProvider> = [
    { title: '名称', dataIndex: 'name', key: 'name', width: 140, render: (v: string, record: LlmProvider) => (
      <Space size={4}>
        <Text strong>{v}</Text>
        {record.tenant_id === null && <Tag>平台</Tag>}
      </Space>
    ) },
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
            {v && (
              <Tooltip title={MODEL_TAG_HINT}>
                <Tag color="gold" style={{ marginInlineEnd: 0 }}>{v}</Tag>
              </Tooltip>
            )}
            {extra > 0 && <Tag style={{ marginInlineEnd: 0 }}>+{extra}</Tag>}
            {!v && <Text type="secondary">-</Text>}
          </Space>
        )
      },
    },
    { title: '状态', dataIndex: 'enabled', key: 'enabled', width: 80, render: (v: boolean) => (v ? <Tag color="success">启用</Tag> : <Tag>停用</Tag>) },
    {
      title: '默认', dataIndex: 'is_active', key: 'is_active', width: 140,
      render: (v: boolean, record: LlmProvider) => (
        <Space size={4}>
          {v ? <Tag color="gold" icon={<CheckCircleOutlined />} style={{ marginInlineEnd: 0 }}>默认</Tag> : null}
          {canSetDefaultRow(record) && (v ? (
            <Popconfirm title={`取消默认“${record.name}”？`} description="取消后未指定模型的请求将使用平台公共模型。"
                        okText="取消默认" okButtonProps={{ danger: true }} cancelText="再想想"
                        onConfirm={() => onCancelDefault(record)}>
              <Button type="link" size="small" loading={settingId === record.id}>取消默认</Button>
            </Popconfirm>
          ) : (
            <Button type="link" size="small"
                    onClick={() => { setSetDefaultError(null); setDefaultTarget(record) }}>设为默认</Button>
          ))}
        </Space>
      ),
    },
    { title: '备注', dataIndex: 'remark', key: 'remark', ellipsis: true, render: (v: string | null) => v || '-' },
    {
      title: '操作', key: 'action', width: 380,
      render: (_: unknown, record: LlmProvider) => {
        const res = testResults[record.id]
        return (
          <Space size={0} wrap>
            {canWriteRow(record) && (
              <Button type="link" size="small" icon={<ThunderboltOutlined />}
                      loading={testingId === record.id} onClick={() => onTest(record)}>
                {testingId === record.id ? '测试连接中…' : '测试连接'}
              </Button>
            )}
            {canWriteRow(record) && (
              <Button type="link" size="small" icon={<EditOutlined />}
                      onClick={() => { setEditing(record); setModalOpen(true) }}>编辑</Button>
            )}
            {canWriteRow(record) && (
              <Button type="link" size="small" icon={<CloudDownloadOutlined />}
                      onClick={() => setDrawerProvider(record)}>管理模型</Button>
            )}
            {canDelete && canWriteRow(record) && (
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

  const hasDefaultRow = rows.some((r) => r.is_active)
  const showCannotSetDefaultNote = canOperate && !isPlatformAdmin && !isIssuer
  const emptyText = canOperate ? (
    <Space orientation="vertical" size={8} style={{ padding: 8 }}>
      <Text>{EMPTY_PROVIDERS}</Text>
      <Button type="primary" icon={<PlusOutlined />}
              onClick={() => { setEditing(null); setModalOpen(true) }}>添加供应商</Button>
    </Space>
  ) : EMPTY_PROVIDERS

  return (
    <>
      {/* §0.10 / GWT-99.1：页名唯一标题在顶栏；无页内标题卡与装饰横幅。
          原 Card extra 的筛选/新建/刷新保留为内容区动作行（GWT-99.3 动作等价） */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
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
                    { value: 'all', label: '全部' },
                    { value: 'active', label: '已设默认' },
                    { value: 'inactive', label: '未设默认' },
                  ]} />
          {canOperate && <Button type="primary" icon={<PlusOutlined />}
                                 onClick={() => { setEditing(null); setModalOpen(true) }}>新建供应商</Button>}
          <Button icon={<ReloadOutlined />} onClick={refreshAll}>刷新</Button>
        </Space>
      </div>

      {!canOperate && (
        <Alert type="info" showIcon style={{ marginBottom: 16 }} title="当前账号不能管理供应商"
               description="需要经办或企业负责人权限。" />
      )}

      {/* T-30 说明句行；绿色「当前默认供应商」横幅（§0.10 装饰横幅）移除，
          其信息量并入本行首行（GWT-99.4 信息不丢） */}
      <Space orientation="vertical" size={2} style={{ display: 'flex', marginBottom: 12 }}>
        {activeLoaded && activeProvider && (
          <Text type="secondary">当前默认供应商：{activeProvider.name}（{activeProvider.model || '-'}）</Text>
        )}
        <Text type="secondary">{DEFAULT_EXPLAIN}</Text>
        {!hasDefaultRow && rows.length > 0 && <Text type="warning">{NO_DEFAULT_HINT}</Text>}
        {showCannotSetDefaultNote && <Text type="warning">{CANNOT_SET_DEFAULT}</Text>}
      </Space>
      {listError && (
        <Alert type="error" showIcon style={{ marginBottom: 16 }} title={LIST_LOAD_FAILED}
               action={<Button size="small" onClick={refreshAll}>重试</Button>} />
      )}
      {(!listError || rows.length > 0) && (
        <Table columns={columns} dataSource={rows.filter((r) =>
          (filterProtocol === 'all' || (r.provider_type || 'openai_compatible') === filterProtocol) &&
          (filterEnabled === 'all' || (filterEnabled === 'enabled') === r.enabled) &&
          (filterActive === 'all' || (filterActive === 'active') === r.is_active)
        )} rowKey="id" loading={loading}
               pagination={false} scroll={{ x: 1400 }}
               locale={{ emptyText }} />
      )}

      <Modal
        open={defaultTarget !== null}
        title="设为默认"
        okText={setting ? '设置中…' : '设为默认'}
        cancelText="取消"
        confirmLoading={setting}
        cancelButtonProps={{ disabled: setting }}
        onOk={() => { if (defaultTarget) applySetDefault(defaultTarget) }}
        onCancel={() => { if (!setting) { setDefaultTarget(null); setSetDefaultError(null) } }}>
        {defaultTarget && (
          <Space orientation="vertical" size={8} style={{ display: 'flex' }}>
            <Text>
              {hasDefaultRow
                ? `将“${defaultTarget.name}”设为默认？未指定模型的请求将默认使用它；“${rows.find((r) => r.is_active)?.name ?? ''}”不再默认。`
                : `将“${defaultTarget.name}”设为默认？未指定模型的请求将默认使用它。`}
            </Text>
            {setDefaultError && <Text type="danger">{setDefaultError}</Text>}
          </Space>
        )}
      </Modal>

      <ProviderWizardModal
        open={modalOpen} editing={editing} presets={presets}
        onClose={() => setModalOpen(false)} onSaved={refreshAll} />
      <ModelSetDrawer
        provider={drawerProvider} onClose={() => setDrawerProvider(null)} onSaved={refreshAll} />
    </>
  )
}

export default LlmProviders
