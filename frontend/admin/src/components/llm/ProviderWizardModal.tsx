/**
 * 供应商新建（向导流）/ 编辑 Modal（工单 80 拆分自 LlmProviders.tsx）
 *
 * 向导：选平台预填 → 拉取模型（probe）→ 勾选 + 指定默认 → 真发 1-token 测连通 → 创建。
 * 编辑态：模型区只读（模型集经 ModelSetDrawer 维护）。
 */
import React, { useMemo, useState } from 'react'
import {
  Button, Col, Form, Input, InputNumber, message, Modal, Radio, Row, Select, Space, Switch, Tag, Typography,
} from 'antd'
import { CloudDownloadOutlined, ThunderboltOutlined } from '@ant-design/icons'
import {
  createLlmProvider, probeModels, probeTest, updateLlmProvider,
  type LlmProvider, type LlmProviderPayload, type PlatformPreset,
} from '../../services/llm'
import { apiErrorMessage, isFormValidateError } from '../../utils/errorMessage'
import { PROTOCOL_NAMES } from './llmShared'

const { Text } = Typography

interface Props {
  open: boolean
  /** null = 新建向导；非空 = 编辑该供应商 */
  editing: LlmProvider | null
  presets: PlatformPreset[]
  onClose: () => void
  onSaved: () => void
}

const ProviderWizardModal: React.FC<Props> = ({ open, editing, presets, onClose, onSaved }) => {
  const [form] = Form.useForm()
  const [submitting, setSubmitting] = useState(false)
  const [probing, setProbing] = useState(false)
  const [probedModels, setProbedModels] = useState<string[]>([])
  const [probeTestResult, setProbeTestResult] = useState<{ ok: boolean; latency_ms: number; error: string } | null>(null)
  const [probeTesting, setProbeTesting] = useState(false)

  // open 沿转 true 时重置表单（编辑态回填）
  React.useEffect(() => {
    if (!open) return
    form.resetFields()
    setProbedModels([])
    setProbeTestResult(null)
    if (editing) {
      form.setFieldsValue({
        name: editing.name,
        provider_type: editing.provider_type || 'openai_compatible',
        base_url: editing.base_url,
        api_key: undefined,
        model: editing.model,
        temperature: editing.temperature ?? undefined,
        timeout: editing.timeout ?? undefined,
        max_retries: editing.max_retries ?? undefined,
        enabled: editing.enabled,
        remark: editing.remark || undefined,
      })
    }
  }, [open, editing, form])

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
      message.success(`拉到 ${data.models.length} 个模型（对话模型 ${data.chat_only_count} 个）`)
    } catch (error) {
      message.error(apiErrorMessage(error, '拉取模型列表失败（可手填模型名兜底）'))
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
      onClose()
      onSaved()
    } catch (error) {
      if (isFormValidateError(error)) return
      message.error(apiErrorMessage(error, editing ? '更新供应商失败' : '创建供应商失败'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      title={editing ? `编辑供应商：${editing.name}` : '新建 LLM 供应商（向导）'}
      open={open} forceRender onOk={onSubmit} onCancel={onClose}
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
  )
}

export default ProviderWizardModal
