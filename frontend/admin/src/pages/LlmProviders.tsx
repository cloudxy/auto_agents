/**
 * LLM 供应商管理页面 - 供应商 CRUD + 激活 + 连通性测试（阶段二）
 *
 * 能力：
 * - 供应商列表（GET /llm/providers，Pydantic 直出数组，无分页后端契约）
 * - 顶部 Alert 提示当前激活供应商（GET /llm/providers/active）
 * - 新建/编辑 Modal：api_key 编辑态留空表示不修改，placeholder 展示脱敏值
 * - 激活（PUT /llm/providers/{id}/activate，已激活禁用）
 * - 测试连通性（POST /llm/providers/{id}/test）：成功 Tag 展示延迟+模型，失败红 Tag Tooltip 展示错误
 * - 删除（仅管理员，Popconfirm 二次确认）
 *
 * 权限与契约约束：
 * - 写操作（新建/激活/测试/编辑/删除）仅 admin 可见（menu:llm 权限），operator/viewer 只读；
 *   operator 虽有 btn:create 但无 menu:llm，直达 /llm 时页面保持只读并展示提示
 * - provider_type 后端白名单仅 openai_compatible，表单隐藏式提交固定值（其余输入必然 422）
 */
import React, { useCallback, useEffect, useState } from 'react'
import {
  Alert, Button, Card, Col, Form, Input, InputNumber, Modal,
  Popconfirm, Row, Space, Switch, Table, Tag, Tooltip, Typography, message,
} from 'antd'
import {
  PlusOutlined, ReloadOutlined, EditOutlined, DeleteOutlined,
  ThunderboltOutlined, CheckCircleOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  fetchLlmProviders, fetchActiveLlmProvider, createLlmProvider, updateLlmProvider,
  deleteLlmProvider, activateLlmProvider, testLlmProvider,
} from '../services/llm'
import type { LlmProvider, LlmProviderPayload, LlmTestResult } from '../services/llm'
import { usePermission } from '../hooks/usePermission'

const { Text } = Typography

/** provider_type 后端白名单唯一合法值（其余任意值必然 422），表单隐藏式提交该固定值 */
const FIXED_PROVIDER_TYPE = 'openai_compatible'

const LlmProviders: React.FC = () => {
  const { hasPermission } = usePermission()
  // 写操作仅 admin（menu:llm）：operator 虽有 btn:create 但无 menu:llm，直达 /llm 时保持只读
  const canOperate = hasPermission('menu:llm')
  const canDelete = hasPermission('btn:delete')  // 删除供应商仅 admin（与 menu:llm 双保险）

  // 列表
  const [rows, setRows] = useState<LlmProvider[]>([])
  const [loading, setLoading] = useState(false)

  // 当前激活供应商（顶部 Alert）
  const [activeProvider, setActiveProvider] = useState<LlmProvider | null>(null)
  const [activeLoaded, setActiveLoaded] = useState(false)

  // 新建/编辑弹窗
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<LlmProvider | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm()

  // 激活/测试进行中的行 id
  const [activatingId, setActivatingId] = useState<number | null>(null)
  const [testingId, setTestingId] = useState<number | null>(null)
  const [testResults, setTestResults] = useState<Record<number, LlmTestResult>>({})

  const loadList = useCallback(async (showSpin = true) => {
    if (showSpin) setLoading(true)
    try {
      const list = await fetchLlmProviders()
      setRows(Array.isArray(list) ? list : [])
    } catch (error) {
      message.error('获取 LLM 供应商列表失败')
    } finally {
      if (showSpin) setLoading(false)
    }
  }, [])

  // 激活接口失败时静默置空（避免把接口异常误报为「未激活」语义提示，仅收起成功 Alert）
  const loadActive = useCallback(async () => {
    try {
      setActiveProvider(await fetchActiveLlmProvider())
    } catch (error) {
      setActiveProvider(null)
    } finally {
      setActiveLoaded(true)
    }
  }, [])

  useEffect(() => {
    loadList()
    loadActive()
  }, [loadList, loadActive])

  const refreshAll = () => {
    loadList(false)
    loadActive()
  }

  // ---------------- 弹窗 ----------------
  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    setModalOpen(true)
  }

  const openEdit = (row: LlmProvider) => {
    setEditing(row)
    form.resetFields()
    form.setFieldsValue({
      name: row.name,
      provider_type: FIXED_PROVIDER_TYPE, // 归一为唯一合法值，规避历史脏数据导致 422
      base_url: row.base_url,
      api_key: undefined, // 编辑态留空表示不修改
      model: row.model,
      temperature: row.temperature ?? undefined,
      timeout: row.timeout ?? undefined,
      max_retries: row.max_retries ?? undefined,
      enabled: row.enabled,
      remark: row.remark || undefined,
    })
    setModalOpen(true)
  }

  const onSubmit = async () => {
    try {
      const values = await form.validateFields()
      setSubmitting(true)
      const payload: LlmProviderPayload = {
        name: values.name.trim(),
        provider_type: values.provider_type?.trim() || FIXED_PROVIDER_TYPE,
        base_url: values.base_url.trim(),
        api_key: values.api_key?.trim() || undefined, // 编辑态留空 = 不修改
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
        await createLlmProvider(payload)
        message.success(`供应商「${payload.name}」已创建`)
      }
      setModalOpen(false)
      refreshAll()
    } catch (error: any) {
      if (error?.errorFields) return // 表单校验失败
      message.error(error?.response?.data?.message || (editing ? '更新供应商失败' : '创建供应商失败'))
    } finally {
      setSubmitting(false)
    }
  }

  // ---------------- 行操作 ----------------
  const onActivate = async (row: LlmProvider) => {
    try {
      setActivatingId(row.id)
      await activateLlmProvider(row.id)
      message.success(`已激活供应商「${row.name}」`)
      refreshAll()
    } catch (error: any) {
      message.error(error?.response?.data?.message || '激活失败')
    } finally {
      setActivatingId(null)
    }
  }

  const onTest = async (row: LlmProvider) => {
    try {
      setTestingId(row.id)
      const res = await testLlmProvider(row.id)
      setTestResults((prev) => ({ ...prev, [row.id]: res }))
      if (res.ok) {
        message.success(`「${row.name}」连通正常（${res.latency_ms ?? '-'}ms）`)
      } else {
        message.error(`「${row.name}」连通失败：${res.error || '未知错误'}`)
      }
    } catch (error: any) {
      // HTTP 层异常（超时/5xx）也落为失败结果，供行内 Tooltip 展示
      const failed: LlmTestResult = {
        ok: false,
        latency_ms: null,
        model: null,
        error: error?.response?.data?.message || error?.message || '请求异常',
      }
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
    } catch (error: any) {
      message.error(error?.response?.data?.message || '删除失败')
    }
  }

  // ---------------- 表格列 ----------------
  const columns: ColumnsType<LlmProvider> = [
    {
      title: '名称', dataIndex: 'name', key: 'name', width: 150,
      render: (v: string) => <Text strong>{v}</Text>,
    },
    {
      title: '类型', dataIndex: 'provider_type', key: 'provider_type', width: 110,
      render: (v: string | null) => (v ? <Tag color="blue">{v}</Tag> : '-'),
    },
    {
      title: 'Base URL', dataIndex: 'base_url', key: 'base_url', width: 220, ellipsis: true,
      render: (v: string) => (
        <Tooltip title={v}><Text code style={{ fontSize: 12 }}>{v}</Text></Tooltip>
      ),
    },
    {
      title: '模型', dataIndex: 'model', key: 'model', width: 180, ellipsis: true,
      render: (v: string) => <Text code style={{ fontSize: 12 }}>{v}</Text>,
    },
    {
      title: '状态', dataIndex: 'enabled', key: 'enabled', width: 90,
      render: (v: boolean) => (v ? <Tag color="success">启用</Tag> : <Tag>停用</Tag>),
    },
    {
      title: '激活', dataIndex: 'is_active', key: 'is_active', width: 110,
      render: (v: boolean) => (v
        ? <Tag color="gold" icon={<CheckCircleOutlined />}>已激活</Tag>
        : <Text type="secondary">-</Text>),
    },
    {
      title: '备注', dataIndex: 'remark', key: 'remark', ellipsis: true,
      render: (v: string | null) => v || '-',
    },
    {
      title: '更新时间', dataIndex: 'updated_at', key: 'updated_at', width: 170,
      render: (v: string | null) => v || '-',
    },
    {
      title: '操作', key: 'action', width: 320,
      render: (_: any, record: LlmProvider) => {
        const res = testResults[record.id]
        return (
          <Space size={0} wrap>
            {canOperate && (
              <Button
                type="link" size="small" icon={<CheckCircleOutlined />}
                disabled={record.is_active}
                loading={activatingId === record.id}
                onClick={() => onActivate(record)}
              >
                激活
              </Button>
            )}
            {canOperate && (
              <Button
                type="link" size="small" icon={<ThunderboltOutlined />}
                loading={testingId === record.id}
                onClick={() => onTest(record)}
              >
                测试连通性
              </Button>
            )}
            {canOperate && (
              <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>
                编辑
              </Button>
            )}
            {canDelete && (
              <Popconfirm
                title="确认删除该供应商？"
                description="删除后依赖该供应商的功能将不可用。"
                okText="删除"
                okButtonProps={{ danger: true }}
                cancelText="取消"
                onConfirm={() => onDelete(record)}
              >
                <Button type="link" danger size="small" icon={<DeleteOutlined />}>删除</Button>
              </Popconfirm>
            )}
            {res && (res.ok
              ? <Tag color="success" style={{ marginLeft: 8 }}>{res.latency_ms ?? '-'}ms · {res.model || '-'}</Tag>
              : (
                <Tooltip title={res.error || '未知错误'}>
                  <Tag color="error" style={{ marginLeft: 8, cursor: 'help' }}>失败</Tag>
                </Tooltip>
              ))}
          </Space>
        )
      },
    },
  ]

  return (
    <>
      {/* 非 admin 只读提示：写操作入口已全部隐藏（menu:llm 守卫） */}
      {!canOperate && (
        <Alert
          type="info" showIcon style={{ marginBottom: 16 }}
          title="仅管理员可管理供应商"
          description="当前账号为只读视图，可查看供应商信息（API Key 已脱敏）；新建/激活/测试/编辑/删除操作仅管理员可用。"
        />
      )}

      {/* 当前激活供应商提示（仅激活接口成功返回后展示，避免误报） */}
      {activeLoaded && (activeProvider ? (
        <Alert
          type="success" showIcon style={{ marginBottom: 16 }}
          title={`当前激活供应商：${activeProvider.name}（${activeProvider.model || '-'}）`}
        />
      ) : (
        <Alert
          type="warning" showIcon style={{ marginBottom: 16 }}
          title="尚未激活任何 LLM 供应商"
          description="AI 采集等功能依赖已激活的 LLM 供应商，请在列表中选择一个并点击「激活」。"
        />
      ))}

      <Card
        title="LLM 供应商配置"
        extra={
          <Space>
            {canOperate && (
              <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建供应商</Button>
            )}
            <Button icon={<ReloadOutlined />} onClick={refreshAll}>刷新</Button>
          </Space>
        }
      >
        <Table
          columns={columns}
          dataSource={rows}
          rowKey="id"
          loading={loading}
          pagination={false}
          scroll={{ x: 1400 }}
          locale={{
            emptyText: canOperate
              ? '暂无 LLM 供应商，点击右上角「新建供应商」添加'
              : '暂无 LLM 供应商',
          }}
        />
      </Card>

      {/* 新建/编辑供应商弹窗（forceRender 保证关闭状态下表单实例可用） */}
      <Modal
        title={editing ? `编辑供应商：${editing.name}` : '新建 LLM 供应商'}
        open={modalOpen}
        forceRender
        onOk={onSubmit}
        onCancel={() => setModalOpen(false)}
        confirmLoading={submitting}
        okText={editing ? '保存' : '创建'}
        cancelText="取消"
        width={560}
      >
        <Form form={form} layout="vertical" initialValues={{ enabled: true }}>
          <Form.Item
            name="name" label="名称"
            rules={[{ required: true, message: '请输入供应商名称' }]}
          >
            <Input placeholder="如：主用大模型" allowClear />
          </Form.Item>
          <Form.Item
            label="供应商类型"
            tooltip="当前后端仅支持 OpenAI 兼容协议，固定为 openai_compatible"
          >
            <Tag color="blue" style={{ marginInlineEnd: 0 }}>openai_compatible</Tag>
          </Form.Item>
          {/* provider_type 隐藏式提交：白名单唯一合法值，避免任意输入被后端 422 拒绝 */}
          <Form.Item name="provider_type" hidden initialValue={FIXED_PROVIDER_TYPE}>
            <Input />
          </Form.Item>
          <Form.Item
            name="base_url" label="Base URL"
            validateTrigger="onBlur"
            rules={[
              { required: true, message: '请输入 Base URL' },
              { pattern: /^https?:\/\/\S+/, message: '必须是 http(s) 地址' },
            ]}
          >
            <Input placeholder="https://api.openai.com/v1" allowClear />
          </Form.Item>
          <Form.Item
            name="api_key" label="API Key"
            tooltip={editing ? '留空表示不修改' : undefined}
            rules={editing ? [] : [{ required: true, message: '请输入 API Key' }]}
          >
            <Input.Password
              placeholder={editing ? (editing.api_key_masked || '留空表示不修改') : 'sk-...'}
              autoComplete="new-password"
            />
          </Form.Item>
          <Form.Item
            name="model" label="模型"
            rules={[{ required: true, message: '请输入模型名称' }]}
          >
            <Input placeholder="如：gpt-4o-mini / qwen-plus" allowClear />
          </Form.Item>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="temperature" label="温度" tooltip="采样温度，通常 0 ~ 2">
                <InputNumber min={0} max={2} step={0.1} style={{ width: '100%' }} placeholder="如 0.7" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="timeout" label="超时（秒）">
                <InputNumber min={1} style={{ width: '100%' }} placeholder="如 60" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="max_retries" label="最大重试">
                <InputNumber min={0} style={{ width: '100%' }} placeholder="如 2" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item
            name="enabled" label="启用" valuePropName="checked"
            tooltip="停用后该供应商不参与调度（不影响已激活状态）"
          >
            <Switch checkedChildren="启用" unCheckedChildren="停用" />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} placeholder="用途说明（可选）" />
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}

export default LlmProviders
