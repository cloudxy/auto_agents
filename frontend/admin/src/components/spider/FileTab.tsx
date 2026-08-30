/**
 * FileTab - 爬虫定义管理（文件清单 + 注册表合并视图；启停/新增/编辑元信息/删除）
 *
 * 数据来源：
 * - fetchSpiderFiles：scrapy/spiders/*.py 文件清单（含未登记文件，registered 标记）
 * - fetchRegistry：DB 注册表（enabled 定义，含 AI 注册的 flow 定义——无对应文件也会列出）
 * 合并策略：文件行补注册表类型；注册表中无文件的定义追加到列表尾部
 *
 * 操作（均仅管理员，后端为最终防线）：
 * - 启停开关（写 spider_definitions.enabled）
 * - 新增定义（name/title/type/description，type：api/web/custom/flow）
 * - 编辑元信息（title/description，PATCH /definitions/{name}/meta）
 * - 删除定义（被历史任务引用时后端拒绝，错误信息透出）
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Table, Button, Tag, Space, Switch, Empty, Typography, message,
  Modal, Form, Input, Select, Popconfirm,
} from 'antd'
import { ReloadOutlined, PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  fetchSpiderFiles, updateDefinition, fetchRegistry,
  createDefinition, updateDefinitionMeta, deleteDefinition,
} from '../../services/spiders'
import type { SpiderFile, SpiderInfo } from '../../services/spiders'

const { Text } = Typography

const TYPE_META: Record<string, { label: string; color: string }> = {
  api: { label: 'API 接口', color: 'purple' },
  web: { label: 'Web 网页', color: 'cyan' },
  custom: { label: '自定义', color: 'geekblue' },
  flow: { label: '流程化', color: 'gold' },
}

/** 合并后的定义行 */
interface DefinitionRow {
  name: string
  title?: string | null
  file: string | null
  size_bytes: number
  registered: boolean
  enabled?: boolean | null
  type?: string
  description?: string
  source?: string
}

export interface FileTabProps {
  isAdmin: boolean
}

export const FileTab: React.FC<FileTabProps> = ({ isAdmin }) => {
  const [rows, setRows] = useState<DefinitionRow[]>([])
  const [loading, setLoading] = useState(false)

  // 新增定义弹窗
  const [createOpen, setCreateOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [createForm] = Form.useForm()

  // 编辑元信息弹窗
  const [editRow, setEditRow] = useState<DefinitionRow | null>(null)
  const [editing, setEditing] = useState(false)
  const [editForm] = Form.useForm()

  const loadRows = useCallback(async () => {
    setLoading(true)
    try {
      const [fileRes, regRes] = await Promise.all([
        fetchSpiderFiles(),
        fetchRegistry().catch(() => ({ spiders: [] as SpiderInfo[] })),
      ])
      const regMap = new Map<string, SpiderInfo>((regRes.spiders || []).map((s) => [s.name, s]))
      const merged: DefinitionRow[] = (fileRes.items || []).map((f: SpiderFile) => {
        const reg = regMap.get(f.name)
        regMap.delete(f.name)
        return {
          name: f.name,
          title: reg?.title || f.title,
          file: f.file,
          size_bytes: f.size_bytes,
          registered: f.registered || !!reg,
          enabled: f.enabled ?? (reg ? true : null),
          type: reg?.type,
          description: reg?.description,
        }
      })
      // 注册表中无对应文件的定义（如 AI 注册的 flow 爬虫）追加到尾部
      regMap.forEach((s) => {
        merged.push({
          name: s.name,
          title: s.title,
          file: null,
          size_bytes: 0,
          registered: true,
          enabled: true,
          type: s.type,
          description: s.description,
        })
      })
      setRows(merged)
    } catch (error) {
      message.error('获取爬虫定义失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadRows()
  }, [loadRows])

  const onToggle = async (row: DefinitionRow, enabled: boolean) => {
    try {
      await updateDefinition(row.name, enabled)
      message.success(`${row.title || row.name} 已${enabled ? '启用' : '停用'}`)
      loadRows()
    } catch (error: any) {
      message.error(error?.response?.data?.message || error?.response?.data?.detail || '启停失败')
    }
  }

  const onCreate = async () => {
    try {
      const values = await createForm.validateFields()
      setCreating(true)
      const def = await createDefinition({
        name: values.name.trim(),
        title: values.title.trim(),
        type: values.type,
        ...(values.description ? { description: values.description } : {}),
      })
      message.success(`定义 ${def.name} 已登记（来源 manual）`)
      setCreateOpen(false)
      loadRows()
    } catch (error: any) {
      if (error?.errorFields) return
      message.error(error?.response?.data?.message || error?.response?.data?.detail || '登记失败')
    } finally {
      setCreating(false)
    }
  }

  const onEditMeta = async () => {
    if (!editRow) return
    try {
      const values = await editForm.validateFields()
      setEditing(true)
      await updateDefinitionMeta(editRow.name, {
        title: values.title.trim(),
        ...(values.description !== undefined ? { description: values.description } : {}),
      })
      message.success(`定义 ${editRow.name} 元信息已更新`)
      setEditRow(null)
      loadRows()
    } catch (error: any) {
      if (error?.errorFields) return
      message.error(error?.response?.data?.message || error?.response?.data?.detail || '更新失败')
    } finally {
      setEditing(false)
    }
  }

  const onDelete = async (row: DefinitionRow) => {
    try {
      await deleteDefinition(row.name)
      message.success(`定义 ${row.name} 已删除`)
      loadRows()
    } catch (error: any) {
      // 被任务引用时后端返回业务错误，透出具体提示
      message.error(error?.response?.data?.message || error?.response?.data?.detail || '删除失败')
    }
  }

  const columns: ColumnsType<DefinitionRow> = useMemo(() => [
    { title: '爬虫', dataIndex: 'name', key: 'name',
      render: (name: string, record: DefinitionRow) => (
        <Space direction="vertical" size={0}>
          <Text strong>{record.title || name}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{name}</Text>
        </Space>
      ),
    },
    {
      title: '文件', dataIndex: 'file', key: 'file',
      render: (v: string | null, record: DefinitionRow) => (
        v ? <Text code>{v}</Text> : <Text type="secondary">无代码文件（注册表登记）</Text>
      ),
    },
    {
      title: '大小', dataIndex: 'size_bytes', key: 'size_bytes', width: 100,
      render: (v: number) => (v ? `${(v / 1024).toFixed(1)} KB` : '-'),
    },
    {
      title: '类型', key: 'type', width: 110,
      render: (_: any, record: DefinitionRow) => {
        if (!record.registered) return <Tag>未登记</Tag>
        const meta = TYPE_META[record.type || ''] || { label: record.type || '-', color: 'default' }
        return <Tag color={meta.color}>{meta.label}</Tag>
      },
    },
    {
      title: '启用', key: 'enabled', width: 90,
      render: (_: any, record: DefinitionRow) => (
        <Switch
          checked={!!record.enabled}
          size="small"
          disabled={!isAdmin || !record.registered}
          onChange={(v) => onToggle(record, v)}
        />
      ),
    },
    {
      title: '操作', key: 'action', width: 150,
      render: (_: any, record: DefinitionRow) =>
        record.registered && isAdmin ? (
          <Space size="small">
            <Button
              type="link" size="small" icon={<EditOutlined />}
              onClick={() => {
                setEditRow(record)
                editForm.setFieldsValue({ title: record.title || record.name, description: record.description || '' })
              }}
            >
              编辑
            </Button>
            <Popconfirm
              title={`确认删除定义 ${record.name}？`}
              description="存在历史任务引用时将被拒绝。"
              okText="删除"
              okButtonProps={{ danger: true }}
              cancelText="取消"
              onConfirm={() => onDelete(record)}
            >
              <Button type="link" danger size="small" icon={<DeleteOutlined />}>删除</Button>
            </Popconfirm>
          </Space>
        ) : (
          <Text type="secondary" style={{ fontSize: 12 }}>
            {record.registered ? '-' : '登记后可管理'}
          </Text>
        ),
    },
  // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [isAdmin, rows])

  return (
    <>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          爬虫定义合并视图（代码文件 + 注册表）；启停即注册表 enabled 开关，停用后不再可调度。flow 类型多由「AI 采集」自动注册。
        </Text>
        <Space>
          {isAdmin && (
            <Button
              type="primary" icon={<PlusOutlined />}
              onClick={() => { createForm.resetFields(); setCreateOpen(true) }}
            >
              新增定义
            </Button>
          )}
          <Button icon={<ReloadOutlined />} onClick={loadRows}>刷新</Button>
        </Space>
      </div>
      <Table
        columns={columns}
        dataSource={rows}
        rowKey="name"
        loading={loading}
        pagination={false}
        locale={{ emptyText: <Empty description="未发现爬虫定义" /> }}
      />

      {/* 新增定义弹窗 */}
      <Modal
        title="新增爬虫定义"
        open={createOpen}
        onOk={onCreate}
        onCancel={() => setCreateOpen(false)}
        confirmLoading={creating}
        okText="登记"
        cancelText="取消"
        destroyOnHidden
        width={520}
      >
        <Form form={createForm} layout="vertical" preserve={false}>
          <Form.Item
            name="name" label="爬虫名"
            rules={[
              { required: true, message: '请输入爬虫名' },
              { pattern: /^[a-zA-Z][a-zA-Z0-9_]{0,49}$/, message: '字母开头，仅字母/数字/下划线，最长 50（需与 scrapy spider name 一致）' },
            ]}
          >
            <Input placeholder="如 my_news_spider" allowClear />
          </Form.Item>
          <Form.Item name="title" label="展示标题" rules={[{ required: true, message: '请输入展示标题' }]}>
            <Input placeholder="如 我的新闻采集" allowClear />
          </Form.Item>
          <Form.Item name="type" label="类型" initialValue="web" tooltip="flow 类型按流程定义（selectors/翻页/详情/过滤）执行，通常由 AI 采集自动注册">
            <Select options={[
              { value: 'api', label: 'API 接口' },
              { value: 'web', label: 'Web 网页' },
              { value: 'custom', label: '自定义采集' },
              { value: 'flow', label: '流程化采集' },
            ]} />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} placeholder="用途说明（可选）" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 编辑元信息弹窗（名称/类型不可改） */}
      <Modal
        title={`编辑定义元信息${editRow ? `：${editRow.name}` : ''}`}
        open={!!editRow}
        onOk={onEditMeta}
        onCancel={() => setEditRow(null)}
        confirmLoading={editing}
        okText="保存"
        cancelText="取消"
        destroyOnHidden
        width={520}
      >
        <Form form={editForm} layout="vertical" preserve={false}>
          <Form.Item label="爬虫名">
            <Input value={editRow?.name} disabled />
          </Form.Item>
          <Form.Item name="title" label="展示标题" rules={[{ required: true, message: '请输入展示标题' }]}>
            <Input allowClear />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}


