/**
 * EditDefinitionModal - 编辑爬虫定义元信息弹窗（FR-103：参数区按类型分形态）
 *
 * 名称/类型不可改（只读回显）。参数区：
 * - api 型：入口地址（每行一个 URL）+ headers 键值行 → params={urls, headers}
 * - flow 型：按定义现有 params 键动态文本输入 → params=动态键值
 * - web/custom（代码型）：锁定句「代码型爬虫请在源码中修改」，无 params 控件
 * 保存成功提示「已保存。后续新任务将使用新定义。」
 */
import React, { useEffect, useState } from 'react'
import { Button, Form, Input, Modal, Space, Typography, message } from 'antd'
import { MinusCircleOutlined, PlusOutlined } from '@ant-design/icons'
import { updateDefinitionMeta } from '../../services/spiders'
import { apiErrorMessage, isFormValidateError } from '../../utils/errorMessage'

const { Text } = Typography

const TYPE_LABEL: Record<string, string> = {
  api: 'API 接口',
  web: 'Web 网页',
  custom: '自定义',
  flow: '流程化',
}

/** 编辑弹窗需要的定义行切片（FileTab DefinitionRow 即满足） */
export interface EditDefinitionRow {
  name: string
  title?: string | null
  type?: string
  description?: string
  params?: Record<string, unknown> | null
}

export interface EditDefinitionModalProps {
  row: EditDefinitionRow | null
  onCancel: () => void
  onSaved: () => void
}

interface HeaderPair {
  key?: string
  value?: string
}

/** api 型参数 → 表单初值（urls 数组转多行文本；headers 转键值行） */
const toApiFormValues = (params: Record<string, unknown> | null | undefined) => ({
  urlsText: Array.isArray(params?.urls) ? (params?.urls as string[]).join('\n') : '',
  headers: Object.entries((params?.headers as Record<string, unknown>) || {}).map(([key, value]) => ({
    key,
    value: value == null ? '' : String(value),
  })),
})

/** 表单值 → api 型 params：多行文本拆 urls（去空行/首尾空白），键值行聚合成 headers（空键丢弃） */
const buildApiParams = (urlsText: string, headers?: HeaderPair[]): { urls: string[]; headers: Record<string, string> } => {
  const urls = String(urlsText || '').split('\n').map((s) => s.trim()).filter(Boolean)
  const headerMap: Record<string, string> = {}
  ;(headers || []).forEach(({ key, value }) => {
    const k = (key || '').trim()
    if (k) headerMap[k] = value ?? ''
  })
  return { urls, headers: headerMap }
}

/** flow 型动态键 → 文本输入初值（非字符串值序列化为 JSON 文本） */
const toFlowFormValues = (params: Record<string, unknown> | null | undefined) => {
  const flowParams: Record<string, string> = {}
  Object.entries(params || {}).forEach(([k, v]) => {
    flowParams[k] = typeof v === 'string' ? v : JSON.stringify(v)
  })
  return { flowParams }
}

export const EditDefinitionModal: React.FC<EditDefinitionModalProps> = ({ row, onCancel, onSaved }) => {
  const [form] = Form.useForm()
  const [editing, setEditing] = useState(false)

  const type = row?.type || ''
  const isApi = type === 'api'
  const isFlow = type === 'flow'
  const isCodeType = !!row && !isApi && !isFlow

  useEffect(() => {
    if (!row) return
    form.setFieldsValue({
      title: row.title || row.name,
      description: row.description || '',
      ...(isApi ? toApiFormValues(row.params) : {}),
      ...(isFlow ? toFlowFormValues(row.params) : {}),
    })
  }, [row, form, isApi, isFlow])

  const onOk = async () => {
    if (!row) return
    try {
      const values = await form.validateFields()
      setEditing(true)
      const payload: { title: string; description?: string; params?: Record<string, unknown> } = {
        title: values.title.trim(),
        ...(values.description !== undefined ? { description: values.description } : {}),
      }
      if (isApi) {
        payload.params = buildApiParams(values.urlsText, values.headers)
      } else if (isFlow) {
        const params: Record<string, string> = {}
        Object.keys(row.params || {}).forEach((k) => {
          const v = values.flowParams?.[k]
          params[k] = typeof v === 'string' ? v : v == null ? '' : String(v)
        })
        if (Object.keys(params).length) payload.params = params
      }
      await updateDefinitionMeta(row.name, payload)
      message.success('已保存。后续新任务将使用新定义。')
      onSaved()
    } catch (error) {
      if (isFormValidateError(error)) return
      message.error(apiErrorMessage(error, '更新失败'))
    } finally {
      setEditing(false)
    }
  }

  return (
    <Modal
      title={`编辑定义元信息${row ? `：${row.name}` : ''}`}
      open={!!row}
      onOk={onOk}
      onCancel={onCancel}
      confirmLoading={editing}
      okText="保存"
      cancelText="取消"
      destroyOnHidden
      width={560}
    >
      <Form form={form} layout="vertical" preserve={false} disabled={!row}>
        <Form.Item label="爬虫名">
          <Input value={row?.name} disabled />
        </Form.Item>
        <Form.Item label="类型">
          <Input value={TYPE_LABEL[type] || type || '-'} disabled />
        </Form.Item>
        <Form.Item name="title" label="展示标题" rules={[{ required: true, message: '请输入展示标题' }]}>
          <Input allowClear />
        </Form.Item>
        <Form.Item name="description" label="描述">
          <Input.TextArea rows={3} />
        </Form.Item>

        {isApi && (
          <>
            <Form.Item
              name="urlsText" label="入口地址"
              rules={[{ required: true, message: '至少填写一个入口地址' }]}
              tooltip="每行一个 URL；保存后后续新任务按此列表采集"
            >
              <Input.TextArea rows={3} placeholder={'https://example.com/a\nhttps://example.com/b'} />
            </Form.Item>
            <Form.Item label="请求头（Headers）" tooltip="随请求发送的自定义 Header，键值成对维护">
              <Form.List name="headers">
                {(fields, { add, remove }) => (
                  <>
                    {fields.map(({ key, name }) => (
                      <Space key={key} align="baseline" style={{ display: 'flex', marginBottom: 4 }}>
                        <Form.Item name={[name, 'key']} rules={[{ required: true, message: '请输入 Header 名' }]} noStyle>
                          <Input placeholder="Header 名（如 Authorization）" style={{ width: 200 }} />
                        </Form.Item>
                        <Form.Item name={[name, 'value']} noStyle>
                          <Input placeholder="值" style={{ width: 220 }} />
                        </Form.Item>
                        <Button
                          type="text" danger size="small" icon={<MinusCircleOutlined />}
                          aria-label="移除请求头" onClick={() => remove(name)}
                        />
                      </Space>
                    ))}
                    <Button
                      type="dashed" icon={<PlusOutlined />} style={{ width: '100%' }}
                      onClick={() => add({ key: '', value: '' })}
                    >
                      添加请求头
                    </Button>
                  </>
                )}
              </Form.List>
            </Form.Item>
          </>
        )}

        {isFlow && (
          Object.keys(row?.params || {}).length > 0 ? (
            Object.keys(row?.params || {}).map((k) => (
              <Form.Item key={k} name={['flowParams', k]} label={k} tooltip="流程定义参数；保存后后续新任务生效">
                <Input allowClear />
              </Form.Item>
            ))
          ) : (
            <Form.Item label="流程参数">
              <Text type="secondary">该定义暂无参数</Text>
            </Form.Item>
          )
        )}

        {isCodeType && (
          <Form.Item label="采集参数">
            <Text type="secondary">代码型爬虫请在源码中修改</Text>
          </Form.Item>
        )}
      </Form>
    </Modal>
  )
}
