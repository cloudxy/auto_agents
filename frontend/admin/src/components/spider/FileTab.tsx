/**
 * FileTab - 爬虫定义管理（文件清单 + 注册表合并视图；启停/新增/编辑元信息/删除）
 *
 * 数据来源：
 * - fetchSpiderFiles：scrapy/spiders/*.py 文件清单（含未登记文件，registered 标记）
 * - fetchRegistry：DB 注册表（enabled 定义，含 AI 注册的 flow 定义——无对应文件也会列出）
 * 合并策略：文件行补注册表类型/参数；注册表中无文件的定义追加到列表尾部
 *
 * 操作（后端为最终防线）：
 * - 启停开关 / 新增定义（仅管理员，写 spider_definitions.enabled）
 * - 编辑元信息（title/description/params，按类型分形态，见 EditDefinitionModal）
 * - 删除定义（被历史任务引用时后端拒绝，拒绝句原样展示在确认弹窗内）
 * 守卫（FR-103）：编辑/删除=经办（tenant_role ∈ operator/owner/admin，RelayGroups 同款写法）
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Table, Button, Tag, Space, Switch, Empty, Typography, message,
  Modal, Form, Input, Select,
} from 'antd'
import { ReloadOutlined, PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import type { ColumnsType } from 'antd/es/table'
import {
  fetchSpiderFiles, updateDefinition, fetchRegistry,
  createDefinition, deleteDefinition,
} from '../../services/spiders'
import type { SpiderFile, SpiderInfo } from '../../services/spiders'
import { apiErrorMessage, isFormValidateError } from '../../utils/errorMessage'
import { useAuthStore } from '../../store/useAuthStore'
import { EditDefinitionModal } from './EditDefinitionModal'

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
  params?: Record<string, unknown> | null
}

export interface FileTabProps {
  isAdmin: boolean
}

/** FR-103 编辑/删除守卫：经办（tenant_role ∈ operator/owner/admin），与 RelayGroups 同写法 */
const META_EDITOR_ROLES = ['operator', 'owner', 'admin']

export const FileTab: React.FC<FileTabProps> = ({ isAdmin }) => {
  const user = useAuthStore((s) => s.user)
  const canManageMeta = META_EDITOR_ROLES.includes(user?.tenant_role || '')
  const navigate = useNavigate()

  const [rows, setRows] = useState<DefinitionRow[]>([])
  const [loading, setLoading] = useState(false)

  // 新增定义弹窗
  const [createOpen, setCreateOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [createForm] = Form.useForm()

  // 编辑元信息弹窗（表单本体在 EditDefinitionModal）
  const [editRow, setEditRow] = useState<DefinitionRow | null>(null)

  // 删除确认弹窗（拒绝句留在弹窗内原样展示）
  const [deleteRow, setDeleteRow] = useState<DefinitionRow | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

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
          params: reg?.params,
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
          params: s.params,
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
    } catch (error) {
      message.error(apiErrorMessage(error, '启停失败'))
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
    } catch (error) {
      if (isFormValidateError(error)) return
      message.error(apiErrorMessage(error, '登记失败'))
    } finally {
      setCreating(false)
    }
  }

  const onDeleteConfirm = async () => {
    if (!deleteRow) return
    try {
      setDeleting(true)
      await deleteDefinition(deleteRow.name)
      message.success(`定义 ${deleteRow.name} 已删除`)
      setDeleteRow(null)
      loadRows()
    } catch (error) {
      // 被历史任务引用时后端返回业务错误：拒绝句原样展示在确认弹窗内（含 #任务号），弹窗保持打开
      setDeleteError(apiErrorMessage(error, '删除失败'))
    } finally {
      setDeleting(false)
    }
  }

  const columns: ColumnsType<DefinitionRow> = useMemo(() => [
    { title: '爬虫', dataIndex: 'name', key: 'name',
      render: (name: string, record: DefinitionRow) => (
        <Space orientation="vertical" size={0}>
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
      render: (_: unknown, record: DefinitionRow) => {
        if (!record.registered) return <Tag>未登记</Tag>
        const meta = TYPE_META[record.type || ''] || { label: record.type || '-', color: 'default' }
        return <Tag color={meta.color}>{meta.label}</Tag>
      },
    },
    {
      title: '启用', key: 'enabled', width: 90,
      render: (_: unknown, record: DefinitionRow) => (
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
      render: (_: unknown, record: DefinitionRow) =>
        record.registered && canManageMeta ? (
          <Space size="small">
            <Button
              type="link" size="small" icon={<EditOutlined />}
              onClick={() => setEditRow(record)}
            >
              编辑
            </Button>
            <Button
              type="link" danger size="small" icon={<DeleteOutlined />}
              onClick={() => { setDeleteError(null); setDeleteRow(record) }}
            >
              删除
            </Button>
          </Space>
        ) : (
          <Text type="secondary" style={{ fontSize: 12 }}>
            {record.registered ? '-' : '登记后可管理'}
          </Text>
        ),
    },
  // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [isAdmin, canManageMeta, rows])

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
        locale={{
          // GWT-103.4/104.3 空态冻结句（edge-states 屏：采集方案 tab）：主句+说明+次链，不是失败句
          emptyText: (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={(
                <Space orientation="vertical" size={0}>
                  <Text>还没有采集方案。</Text>
                  <Text type="secondary">创建入口在 AI 采集规划。</Text>
                </Space>
              )}
            >
              <Button type="primary" onClick={() => navigate('/ai')}>去 AI 采集规划</Button>
            </Empty>
          ),
        }}
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

      {/* 编辑元信息弹窗（名称/类型不可改；参数区按类型分形态） */}
      <EditDefinitionModal
        row={editRow}
        onCancel={() => setEditRow(null)}
        onSaved={() => { setEditRow(null); loadRows() }}
      />

      {/* 删除确认弹窗：被引用时后端拒绝句原样展示（含 #任务号），弹窗保持打开 */}
      <Modal
        title={`确认删除定义${deleteRow ? `：${deleteRow.name}` : ''}`}
        open={!!deleteRow}
        onOk={onDeleteConfirm}
        onCancel={() => setDeleteRow(null)}
        confirmLoading={deleting}
        okText="删除"
        okButtonProps={{ danger: true }}
        cancelText="取消"
        destroyOnHidden
        width={520}
      >
        <Space orientation="vertical" size={4}>
          <Text>删除后定义不可恢复；存在历史任务引用时将被拒绝。</Text>
          {deleteError && <Text type="danger" data-testid="delete-reject-reason">{deleteError}</Text>}
        </Space>
      </Modal>
    </>
  )
}


