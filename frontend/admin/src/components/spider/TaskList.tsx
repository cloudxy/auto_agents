/**
 * TaskList - 任务列表表格 + 操作列
 */
import React from 'react'
import { Table, Button, Tag, Space, Popconfirm, Tooltip, Typography, Select } from 'antd'
import {
  PlayCircleOutlined, PauseCircleOutlined, StopOutlined, CaretRightOutlined,
  EyeOutlined, FileTextOutlined, DeleteOutlined, StarOutlined, LoadingOutlined,
  SyncOutlined, PlusOutlined, ReloadOutlined, EditOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { STATUS_META, PRIORITY_META } from './types'
import type { Task, SpiderMap } from './types'

const { Text } = Typography

export interface TaskListProps {
  tasks: Task[]
  loading: boolean
  total: number
  page: number
  pageSize: number
  spiderMap: SpiderMap
  canCreate: boolean
  canDelete: boolean
  canOperate: boolean
  priorityFilter: string | undefined
  onPriorityFilterChange: (v: string | undefined) => void
  statusFilter: string | undefined
  onStatusFilterChange: (v: string | undefined) => void
  spiderFilter: string | undefined
  onSpiderFilterChange: (v: string | undefined) => void
  spiderOptions: { value: string; label: string }[]
  onPaginationChange: (page: number, pageSize: number) => void
  onRun: (task: Task) => void
  onCreateNew: () => void
  onPause: (task: Task) => void
  onResume: (task: Task) => void
  onStop: (task: Task) => void
  onDelete: (task: Task) => void
  onSaveTemplate: (task: Task) => void
  onViewLog: (task: Task) => void
  onViewResult: (task: Task) => void
  onEdit: (task: Task) => void
  onRefresh: () => void
}

export const TaskList: React.FC<TaskListProps> = ({
  tasks, loading, total, page, pageSize, spiderMap,
  canCreate, canDelete, canOperate,
  priorityFilter, onPriorityFilterChange,
  statusFilter, onStatusFilterChange,
  spiderFilter, onSpiderFilterChange, spiderOptions,
  onPaginationChange,
  onRun, onCreateNew, onPause, onResume, onStop, onDelete,
  onSaveTemplate, onViewLog, onViewResult, onEdit, onRefresh,
}) => {
  const TYPE_META: Record<string, { label: string; color: string }> = {
    api: { label: 'API 接口', color: 'purple' },
    web: { label: 'Web 网页', color: 'cyan' },
    custom: { label: '自定义', color: 'geekblue' },
    flow: { label: '流程化', color: 'gold' },
  }
  const columns: ColumnsType<Task> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 70 },
    {
      title: '采集方案',
      dataIndex: 'spider_name',
      key: 'spider_name',
      render: (name: string) => (
        <Space direction="vertical" size={0}>
          <Text strong>{spiderMap[name]?.title || name}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{name}</Text>
        </Space>
      ),
    },
    {
      title: '类型',
      key: 'type',
      width: 110,
      render: (_: unknown, record: Task) => {
        const type = spiderMap[record.spider_name]?.type
        if (!type) return '-'
        const meta = TYPE_META[type] || { label: type, color: 'default' }
        return <Tag color={meta.color}>{meta.label}</Tag>
      },
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      key: 'priority',
      width: 90,
      render: (priority: string) => {
        const meta = PRIORITY_META[priority] || PRIORITY_META.normal
        return <Tag color={meta.color}>{meta.label}</Tag>
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 150,
      render: (status: string, record: Task) => {
        const meta = STATUS_META[status] || { label: status, color: 'default' }
        const spinning = status === 'running'
          ? <LoadingOutlined spin style={{ marginRight: 6 }} />
          : status === 'pending'
            ? <SyncOutlined spin style={{ marginRight: 6 }} />
            : null
        const tag = (
          <Tag color={meta.color} icon={spinning}>
            {meta.label}
            {(record.retry_count || 0) > 0 ? `（重试${record.retry_count}）` : ''}
          </Tag>
        )
        // 失败原因直显（U1-6）：不再只藏 Tag 的 hover 里
        return record.error_message ? (
          <Space direction="vertical" size={0}>
            <Tooltip title={record.error_message}>{tag}</Tooltip>
            <Text type="danger" ellipsis style={{ maxWidth: 150, fontSize: 12 }} title={record.error_message}>
              {record.error_message}
            </Text>
          </Space>
        ) : tag
      },
    },
    { title: '采集结果', dataIndex: 'result_count', key: 'result_count', width: 90 },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 180 },
    {
      title: '操作',
      key: 'action',
      width: 380,
      render: (_: unknown, record: Task) => (
        <Space size="small" wrap>
          {canCreate && (
            <Tooltip title="以该任务的参数再次运行">
              <Button
                type="link"
                size="small"
                icon={<PlayCircleOutlined />}
                disabled={record.status === 'running'}
                onClick={() => onRun(record)}
              >
                再次运行
              </Button>
            </Tooltip>
          )}
          {canOperate && record.status === 'running' && (
            <>
              <Popconfirm
                title="确认暂停该任务？"
                description="暂停后将跳过后续请求，直到点击恢复。"
                okText="暂停"
                onConfirm={() => onPause(record)}
              >
                <Button type="link" size="small" icon={<PauseCircleOutlined />}>
                  暂停
                </Button>
              </Popconfirm>
              <Popconfirm
                title="确认终止该任务？"
                description="终止后将立即停止，任务置为失败状态。"
                okText="终止"
                okButtonProps={{ danger: true }}
                onConfirm={() => onStop(record)}
              >
                <Button type="link" danger size="small" icon={<StopOutlined />}>
                  终止
                </Button>
              </Popconfirm>
            </>
          )}
          {canOperate && record.status === 'running' && (
            <Tooltip title="若任务已暂停，点击恢复继续采集（未暂停时点击无副作用）">
              <Button
                type="link"
                size="small"
                icon={<CaretRightOutlined />}
                onClick={() => onResume(record)}
              >
                恢复
              </Button>
            </Tooltip>
          )}
          <Button
            type="link"
            size="small"
            icon={<EyeOutlined />}
            disabled={!record.result_count}
            onClick={() => onViewResult(record)}
          >
            结果
          </Button>
          <Button
            type="link"
            size="small"
            icon={<FileTextOutlined />}
            onClick={() => onViewLog(record)}
          >
            日志
          </Button>
          {canOperate && record.status === 'pending' && (
            <Button
              type="link"
              size="small"
              icon={<EditOutlined />}
              onClick={() => onEdit(record)}
            >
              编辑
            </Button>
          )}
          {canCreate && (
            <Button
              type="link"
              size="small"
              icon={<StarOutlined />}
              onClick={() => onSaveTemplate(record)}
            >
              收藏
            </Button>
          )}
          {canDelete && (
            <Popconfirm
              title="确认删除该任务？"
              description="将级联删除该任务的全部采集结果，且不可恢复。"
              okText="删除"
              okButtonProps={{ danger: true }}
              cancelText="取消"
              disabled={record.status === 'running'}
              onConfirm={() => onDelete(record)}
            >
              <Button
                type="link"
                danger
                size="small"
                icon={<DeleteOutlined />}
                disabled={record.status === 'running'}
              >
                删除
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  return (
    <>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
        <Space wrap>
          <Select
            allowClear
            placeholder="按状态筛选"
            style={{ width: 140 }}
            value={statusFilter}
            onChange={(v) => onStatusFilterChange(v)}
            options={[
              { value: 'pending', label: '状态：待执行' },
              { value: 'running', label: '状态：运行中' },
              { value: 'completed', label: '状态：已完成' },
              { value: 'failed', label: '状态：失败' },
            ]}
          />
          <Select
            allowClear
            showSearch
            placeholder="按采集方案筛选"
            style={{ width: 180 }}
            value={spiderFilter}
            onChange={(v) => onSpiderFilterChange(v)}
            options={spiderOptions}
          />
          <Select
            allowClear
            placeholder="按优先级筛选"
            style={{ width: 140 }}
            value={priorityFilter}
            onChange={(v) => onPriorityFilterChange(v)}
            options={[
              { value: 'high', label: '优先级：高' },
              { value: 'normal', label: '优先级：普通' },
              { value: 'low', label: '优先级：低' },
            ]}
          />
        </Space>
        <Space>
          {canCreate && (
            <Button type="primary" icon={<PlusOutlined />} onClick={onCreateNew}>
              新增任务
            </Button>
          )}
          <Button icon={<ReloadOutlined />} onClick={onRefresh}>刷新</Button>
        </Space>
      </div>
      <Table
        columns={columns}
        dataSource={tasks}
        rowKey="id"
        loading={loading}
        pagination={{
          total,
          current: page,
          pageSize,
          showSizeChanger: false,
          showTotal: (t) => `共 ${t} 条任务`,
          onChange: (p, ps) => onPaginationChange(p, ps),
        }}
      />
    </>
  )
}
