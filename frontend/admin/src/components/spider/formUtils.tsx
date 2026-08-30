/**
 * 爬虫管理模块 - 共享表单工具（动态参数字段、参数收集）
 */
import React from 'react'
import {
  Form, Input, Select, InputNumber, Button, Space, Collapse,
} from 'antd'
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons'
import type { SpiderParamField } from './types'

/** 可增删的选择器规则行（字段名 + 类型 + 表达式），自定义采集与详情页字段规则共用 */
export const SelectorRowList: React.FC<{ name: string; addLabel?: string }> = ({ name, addLabel }) => (
  <Form.List name={name}>
    {(rows, { add, remove }) => (
      <>
        {rows.map(({ key, name: rowName, ...rest }) => (
          <Space key={key} align="baseline" style={{ display: 'flex', marginBottom: 4 }}>
            <Form.Item {...rest} name={[rowName, 'name']} noStyle
              rules={[{ required: true, message: '字段名必填' }]}>
              <Input placeholder="字段名，如 title" style={{ width: 140 }} />
            </Form.Item>
            <Form.Item {...rest} name={[rowName, 'type']} noStyle initialValue="css">
              <Select style={{ width: 100 }} options={[
                { value: 'css', label: 'CSS' },
                { value: 'xpath', label: 'XPath' },
                { value: 'regex', label: '正则' },
              ]} />
            </Form.Item>
            <Form.Item {...rest} name={[rowName, 'expr']} noStyle
              rules={[{ required: true, message: '表达式必填' }]}>
              <Input placeholder="表达式，如 h1::text" style={{ width: 260 }} />
            </Form.Item>
            <DeleteOutlined onClick={() => remove(rowName)} />
          </Space>
        ))}
        <Button type="dashed" block icon={<PlusOutlined />} onClick={() => add({ type: 'css' })}>
          {addLabel || '添加提取规则'}
        </Button>
      </>
    )}
  </Form.List>
)

/** 流程段折叠区（分页 / 详情页 / 条件过滤），未配置时不产生契约段 */
const renderFlowField = (field: SpiderParamField) => {
  if (field.kind === 'pagination') {
    return (
      <Form.Item key={field.name} label={field.label} tooltip={field.help}>
        <Collapse size="small" items={[{
          key: 'pagination',
          label: '自动翻页（可选）',
          children: (
            <>
              <Form.Item name={['param_pagination', 'selector']} label="下一页选择器" style={{ marginBottom: 8 }}>
                <Input placeholder="如 a.next::attr(href)" />
              </Form.Item>
              <Form.Item name={['param_pagination', 'type']} label="选择器类型" initialValue="css" style={{ marginBottom: 8 }}>
                <Select options={[
                  { value: 'css', label: 'CSS' },
                  { value: 'xpath', label: 'XPath' },
                ]} />
              </Form.Item>
              <Form.Item name={['param_pagination', 'max_pages']} label="最大页数" initialValue={10} style={{ marginBottom: 0 }}>
                <InputNumber min={1} max={100} />
              </Form.Item>
            </>
          ),
        }]} />
      </Form.Item>
    )
  }
  if (field.kind === 'detail') {
    return (
      <Form.Item key={field.name} label={field.label} tooltip={field.help}>
        <Collapse size="small" items={[{
          key: 'detail',
          label: '详情页二次采集（可选）',
          children: (
            <>
              <Form.Item name={['param_detail', 'list_selector']} label="列表项选择器" style={{ marginBottom: 8 }}>
                <Input placeholder="如 li.news（每项内提取详情链接）" />
              </Form.Item>
              <Form.Item name={['param_detail', 'url_selector']} label="链接选择器" tooltip="XPath，相对列表项节点"
                style={{ marginBottom: 8 }}>
                <Input placeholder="如 .//a/@href" />
              </Form.Item>
              <Form.Item label="详情页提取规则" style={{ marginBottom: 0 }}>
                <SelectorRowList name="param_detail_selectors" addLabel="添加详情字段规则" />
              </Form.Item>
            </>
          ),
        }]} />
      </Form.Item>
    )
  }
  // filters：条件过滤行（字段 / 操作符 / 值）
  return (
    <Form.Item key={field.name} label={field.label} tooltip={field.help}>
      <Form.List name="param_filters">
        {(rows, { add, remove }) => (
          <>
            {rows.map(({ key, name: rowName, ...rest }) => (
              <Space key={key} align="baseline" style={{ display: 'flex', marginBottom: 4 }}>
                <Form.Item {...rest} name={[rowName, 'field']} noStyle
                  rules={[{ required: true, message: '字段名必填' }]}>
                  <Input placeholder="字段名，如 title" style={{ width: 140 }} />
                </Form.Item>
                <Form.Item {...rest} name={[rowName, 'op']} noStyle initialValue="contains">
                  <Select style={{ width: 100 }} options={[
                    { value: 'contains', label: '包含' },
                    { value: 'equals', label: '等于' },
                    { value: 'regex', label: '正则' },
                  ]} />
                </Form.Item>
                <Form.Item {...rest} name={[rowName, 'value']} noStyle
                  rules={[{ required: true, message: '值必填' }]}>
                  <Input placeholder="匹配值，如 Python" style={{ width: 260 }} />
                </Form.Item>
                <DeleteOutlined onClick={() => remove(rowName)} />
              </Space>
            ))}
            <Button type="dashed" block icon={<PlusOutlined />} onClick={() => add({ op: 'contains' })}>
              添加过滤条件
            </Button>
          </>
        )}
      </Form.List>
    </Form.Item>
  )
}

/** 动态参数字段渲染（新增任务弹窗与定时任务弹窗共用） */
export const renderParamFields = (fields?: SpiderParamField[]) =>
  (fields || []).map((field) =>
    field.kind === 'selectors' ? (
      <Form.Item key={field.name} label={field.label} tooltip={field.help} required={field.required}>
        <SelectorRowList name={`param_${field.name}`} />
      </Form.Item>
    ) : field.kind === 'pagination' || field.kind === 'detail' || field.kind === 'filters' ? (
      renderFlowField(field)
    ) : (
    <Form.Item
      key={field.name}
      name={`param_${field.name}`}
      label={field.label}
      tooltip={field.help}
      rules={field.required ? [{ required: true, message: `请填写${field.label}` }] : []}
      initialValue={field.default ?? undefined}
    >
      {field.kind === 'urls' ? (
        <Input.TextArea rows={4} placeholder={field.help || '每行一个 URL'} />
      ) : field.kind === 'json' ? (
        <Input.TextArea rows={3} placeholder={field.help || '{"key": "value"}'} />
      ) : field.kind === 'select' ? (
        <Select options={field.options || []} placeholder={`请选择${field.label}`} />
      ) : (
        <Input placeholder={field.help || ''} />
      )}
    </Form.Item>
    )
  )

/** 从表单值收集任务参数对象（与后端 params 契约一致） */
export const collectParams = (
  values: Record<string, any>,
  fields?: SpiderParamField[]
): Record<string, any> | string => {
  const paramsObj: Record<string, any> = {}
  for (const field of fields || []) {
    if (field.kind === 'pagination') {
      const p = values.param_pagination || {}
      const selector = String(p.selector || '').trim()
      if (selector) {
        paramsObj.pagination = { selector, type: p.type || 'css', max_pages: Number(p.max_pages) || 10 }
      }
      continue
    }
    if (field.kind === 'detail') {
      const d = values.param_detail || {}
      const listSelector = String(d.list_selector || '').trim()
      const urlSelector = String(d.url_selector || '').trim()
      const rows = Array.isArray(values.param_detail_selectors)
        ? values.param_detail_selectors
            .filter((r: any) => r && String(r.name || '').trim() && String(r.expr || '').trim())
            .map((r: any) => ({ name: String(r.name).trim(), type: r.type || 'css', expr: String(r.expr).trim() }))
        : []
      if (listSelector && urlSelector) {
        paramsObj.detail = { list_selector: listSelector, url_selector: urlSelector, ...(rows.length ? { selectors: rows } : {}) }
      }
      continue
    }
    if (field.kind === 'filters') {
      const rows = Array.isArray(values.param_filters)
        ? values.param_filters
            .filter((r: any) => r && String(r.field || '').trim() && String(r.value || '').trim())
            .map((r: any) => ({ field: String(r.field).trim(), op: r.op || 'contains', value: String(r.value).trim() }))
        : []
      if (rows.length) paramsObj.filters = rows
      continue
    }
    const raw = values[`param_${field.name}`]
    if (raw === undefined || raw === '') continue
    if (field.kind === 'urls') {
      paramsObj[field.name] = String(raw).split('\n').map((s) => s.trim()).filter(Boolean)
    } else if (field.kind === 'selectors') {
      const rows = Array.isArray(raw)
        ? raw
            .filter((r: any) => r && String(r.name || '').trim() && String(r.expr || '').trim())
            .map((r: any) => ({ name: String(r.name).trim(), type: r.type || 'css', expr: String(r.expr).trim() }))
        : []
      if (field.required && rows.length === 0) {
        return `请至少添加一条${field.label}`
      }
      paramsObj[field.name] = rows
    } else if (field.kind === 'json') {
      try {
        paramsObj[field.name] = JSON.parse(String(raw))
      } catch {
        return `${field.label} 不是合法的 JSON`
      }
    } else {
      paramsObj[field.name] = raw
    }
  }
  return paramsObj
}
