/**
 * AI 方案展示与编辑组件（从 pages/AiPlans.tsx 拆出，期 4 前端治理）
 *
 * - SelectorTable：选择器规则表（只读展示）
 * - FlowPreview：flow_generic 方案结构可视化（翻页/详情页/渲染/过滤 + 规则表）
 * - FilterRuleList：条件过滤行编辑（Form.List，字段/操作符/值）
 */
import React from 'react'
import { Button, Descriptions, Form, Input, Select, Space, Table, Tag, Typography } from 'antd'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import type { FlowConfig, FlowSelector } from '../../services/ai'

const { Text } = Typography

const SELECTOR_TYPE_COLORS: Record<string, string> = { css: 'cyan', xpath: 'purple', regex: 'orange' }
const FILTER_OP_LABELS: Record<string, string> = { contains: '包含', equals: '等于', regex: '正则' }

// ----------------------------------------------------------------------
// 展示组件：选择器规则表
// ----------------------------------------------------------------------
export const SelectorTable: React.FC<{ rows: FlowSelector[]; title: string }> = ({ rows, title }) => (
  <div style={{ marginBottom: 12 }}>
    <Text type="secondary" style={{ display: 'block', marginBottom: 6 }}>{title}</Text>
    <Table
      size="small"
      dataSource={rows}
      rowKey={(_, index) => String(index)}
      pagination={false}
      columns={[
        { title: '字段名', dataIndex: 'name', width: 140, render: (v: string) => <Text code>{v}</Text> },
        {
          title: '类型', dataIndex: 'type', width: 90,
          render: (v: string) => <Tag color={SELECTOR_TYPE_COLORS[v] || 'default'}>{v}</Tag>,
        },
        { title: '表达式', dataIndex: 'expr', render: (v: string) => <Text code style={{ fontSize: 12 }}>{v}</Text> },
      ]}
    />
  </div>
)

// ----------------------------------------------------------------------
// 展示组件：flow 结构可视化
// ----------------------------------------------------------------------
export const FlowPreview: React.FC<{ flow: FlowConfig }> = ({ flow }) => (
  <div>
    <Descriptions size="small" column={2} bordered style={{ marginBottom: 12 }}>
      <Descriptions.Item label="自动翻页">
        {flow.pagination
          ? `${flow.pagination.max_pages} 页 · ${flow.pagination.type}：${flow.pagination.selector}`
          : '未配置'}
      </Descriptions.Item>
      <Descriptions.Item label="详情页采集">
        {flow.detail
          ? `列表项 ${flow.detail.list_selector} → 链接 ${flow.detail.url_selector}`
          : '未配置'}
      </Descriptions.Item>
      <Descriptions.Item label="JS 渲染">{flow.render_js ? '启用（Playwright）' : '关闭'}</Descriptions.Item>
      <Descriptions.Item label="过滤条件">{flow.filters?.length || 0} 条</Descriptions.Item>
    </Descriptions>
    <SelectorTable rows={flow.selectors || []} title="列表页提取规则" />
    {flow.detail && flow.detail.selectors && flow.detail.selectors.length > 0 && (
      <SelectorTable rows={flow.detail.selectors} title="详情页提取规则" />
    )}
    {flow.filters && flow.filters.length > 0 && (
      <div style={{ marginBottom: 12 }}>
        <Text type="secondary" style={{ display: 'block', marginBottom: 6 }}>条件过滤</Text>
        <Space wrap>
          {flow.filters.map((f, i) => (
            <Tag key={i} color="blue">
              {f.field} {FILTER_OP_LABELS[f.op] || f.op} 「{f.value}」
            </Tag>
          ))}
        </Space>
      </div>
    )}
  </div>
)

// ----------------------------------------------------------------------
// 编辑组件：过滤条件行（字段/操作符/值）
// ----------------------------------------------------------------------
export const FilterRuleList: React.FC = () => (
  <Form.List name="filters">
    {(rows, { add, remove }) => (
      <>
        {rows.map(({ key, name: rowName, ...rest }) => (
          <Space key={key} align="baseline" style={{ display: 'flex', marginBottom: 4 }}>
            <Form.Item {...rest} name={[rowName, 'field']} noStyle
              rules={[{ required: true, message: '字段名必填' }]}>
              <Input placeholder="字段名，如 title" style={{ width: 130 }} />
            </Form.Item>
            <Form.Item {...rest} name={[rowName, 'op']} noStyle initialValue="contains">
              <Select style={{ width: 90 }} options={[
                { value: 'contains', label: '包含' },
                { value: 'equals', label: '等于' },
                { value: 'regex', label: '正则' },
              ]} />
            </Form.Item>
            <Form.Item {...rest} name={[rowName, 'value']} noStyle
              rules={[{ required: true, message: '值必填' }]}>
              <Input placeholder="匹配值，如 Python" style={{ width: 220 }} />
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
)
