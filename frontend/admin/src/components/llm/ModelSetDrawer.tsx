/**
 * 供应商模型集管理 Drawer（工单 80 拆分自 LlmProviders.tsx）
 *
 * 全量提交模型集（tier/priority/默认/enabled）+ fetch diff 三区（新增/已有/远端消失）
 * + 行级连通测试。provider 变化时拉取模型列表。
 */
import React, { useCallback, useEffect, useState } from 'react'
import {
  Alert, Button, Drawer, InputNumber, message, Radio, Select, Space, Spin, Switch, Table, Tag, Typography,
} from 'antd'
import { CloudDownloadOutlined } from '@ant-design/icons'
import {
  fetchModelsDiff, getLlmProviderModels, putLlmProviderModels, testLlmProviderModel,
  type LlmProvider, type ProviderModelRow,
} from '../../services/llm'
import { apiErrorMessage } from '../../utils/errorMessage'
import { HEALTH_TAGS } from './llmShared'

const { Text } = Typography

interface Props {
  provider: LlmProvider | null
  onClose: () => void
  /** 保存成功后通知父级刷新（默认模型快照冗余列在列表） */
  onSaved: () => void
}

const ModelSetDrawer: React.FC<Props> = ({ provider, onClose, onSaved }) => {
  const [models, setModels] = useState<ProviderModelRow[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [diff, setDiff] = useState<{ new: string[]; existing: string[]; vanished: string[] } | null>(null)
  const [diffLoading, setDiffLoading] = useState(false)
  const [rowTesting, setRowTesting] = useState<string | null>(null)

  useEffect(() => {
    if (!provider) return
    setDiff(null)
    setLoading(true)
    getLlmProviderModels(provider.id)
      .then(setModels)
      .catch((error) => message.error(apiErrorMessage(error, '模型列表加载失败')))
      .finally(() => setLoading(false))
  }, [provider])

  const onFetchDiff = useCallback(async () => {
    if (!provider) return
    try {
      setDiffLoading(true)
      setDiff(await fetchModelsDiff(provider.id))
    } catch (error) {
      message.error(apiErrorMessage(error, '重新拉取失败'))
    } finally {
      setDiffLoading(false)
    }
  }, [provider])

  const importNewModels = async () => {
    if (!diff || !provider) return
    const fresh = diff.new.filter((id) => !models.some((m) => m.model_id === id))
    setModels((prev) => [
      ...prev,
      ...fresh.map((model_id) => ({
        model_id, alias: '', model_tier: 'basic' as const, priority: 100,
        is_default: false, enabled: true, health_status: 'unknown' as const,
      })),
    ])
    message.success(`已导入 ${fresh.length} 个新模型，正在用供应商 API Key 自动连通测试…`)
    // 供应商级 API Key 对全部模型生效（模型行不单独存 key）：导入后立即
    // 逐个 1-token 实测，健康态即时呈现——key 是否配置正确一目了然
    for (const model_id of fresh) {
      try {
        setRowTesting(model_id)
        const res = await testLlmProviderModel(provider.id, model_id)
        patchModel(model_id, {
          health_status: res.health_status as ProviderModelRow['health_status'],
          last_latency_ms: res.latency_ms,
        })
        if (!res.ok && /401|403|Unauthorized|api[_ ]?key/i.test(res.error || '')) {
          message.warning(`${model_id}：鉴权失败（${res.error}）——请检查供应商 API Key`)
        }
      } catch (e) {
        message.error(apiErrorMessage(e, `${model_id} 测试请求异常`))
      } finally {
        setRowTesting(null)
      }
    }
  }

  const patchModel = (modelId: string, patch: Partial<ProviderModelRow>) => {
    setModels((prev) => prev.map((m) => (m.model_id === modelId ? { ...m, ...patch } : m)))
  }

  const onRowTest = async (modelId: string) => {
    if (!provider) return
    try {
      setRowTesting(modelId)
      const res = await testLlmProviderModel(provider.id, modelId)
      patchModel(modelId, { health_status: res.health_status as ProviderModelRow['health_status'], last_latency_ms: res.latency_ms })
      res.ok ? message.success(`${modelId} 连通（${res.latency_ms}ms）`) : message.error(`${modelId}：${res.error}`)
    } catch (error) {
      message.error(apiErrorMessage(error, '测试请求异常'))
    } finally {
      setRowTesting(null)
    }
  }

  const save = async () => {
    if (!provider) return
    if (models.filter((m) => m.is_default).length > 1) {
      message.error('默认模型至多一个')
      return
    }
    try {
      setSaving(true)
      await putLlmProviderModels(provider.id, models.map((m) => ({
        model_id: m.model_id, alias: m.alias, model_tier: m.model_tier,
        priority: m.priority, is_default: m.is_default, enabled: m.enabled,
      })))
      message.success('模型集已保存')
      onClose()
      onSaved()
    } catch (error) {
      message.error(apiErrorMessage(error, '保存失败'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Drawer
      title={`管理模型：${provider?.name ?? ''}`} width={720} open={!!provider}
      onClose={onClose}
      extra={<Space>
        <Button icon={<CloudDownloadOutlined />} loading={diffLoading} onClick={onFetchDiff}>重新拉取 diff</Button>
        <Button type="primary" loading={saving} onClick={save}>保存（全量提交）</Button>
      </Space>}
    >
      {diff && (
        <Alert type="info" showIcon style={{ marginBottom: 12 }}
               message={
                 <Space wrap>
                   <span>新增 {diff.new.length} / 已有 {diff.existing.length} / 远端已消失 {diff.vanished.length}</span>
                   {diff.new.length > 0 && <Button size="small" onClick={importNewModels}>导入新增（自动测试）</Button>}
                   {diff.vanished.length > 0 && <Text type="warning">建议清理：{diff.vanished.join(', ')}</Text>}
                 </Space>
               } />
      )}
      {loading ? <Spin /> : (
        <Table
          rowKey="model_id" size="small" pagination={false}
          dataSource={models}
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
              <Radio checked={v} onChange={() => setModels((prev) => prev.map((m) => ({ ...m, is_default: m.model_id === r.model_id })))} />
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
              <Button size="small" type="link" danger onClick={() => setModels((prev) => prev.filter((m) => m.model_id !== r.model_id))}>删</Button>
            )},
          ]}
        />
      )}
    </Drawer>
  )
}

export default ModelSetDrawer
