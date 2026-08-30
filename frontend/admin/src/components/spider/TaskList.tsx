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
  spiderMap: SpiderMap
  canCreate: boolean
  canDelete: boolean
  canOperate: boolean
  priorityFilter: string | undefined
  onPriorityFilterChange: (v: string | undefined) => void
  onRun: (spiderName: string) => void
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
  tasks, loading, total, spiderMap,
  canCreate, canDelete, canOperate,
  priorityFilter, onPriorityFilterChange,
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
      title: '爬虫',
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
      render: (_: any, record: Task) => {
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
      width: 120,
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
        return record.error_message
          ? <Tooltip title={record.error_message}>{tag}</Tooltip>
          : tag
      },
    },
    { title: '采集结果', dataIndex: 'result_count', key: 'result_count', width: 90 },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 180 },
    {
      title: '操作',
      key: 'action',
      width: 380,
      render: (_: any, record: Task) => (
        <Space size="small" wrap>
          {canCreate && (
            <Button
              type="link"
              size="small"
              icon={<PlayCircleOutlined />}
              disabled={record.status === 'running'}
              onClick={() => onRun(record.spider_name)}
            >
              运行
            </Button>
          )}
          {canOperate && record.status === 'running' && (
            <>
              <Popconfirm
                title="确认暂停该任务？"
                description="暂停后爬虫将跳过后续请求，直到点击恢复。"
                okText="暂停"
                onConfirm={() => onPause(record)}
              >
                <Button type="link" size="small" icon={<PauseCircleOutlined />}>
                  暂停
                </Button>
              </Popconfirm>
              <Popconfirm
                title="确认终止该任务？"
                description="终止后爬虫将立即停止，任务置为失败状态。"
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
            <Button
              type="link"
              size="small"
              icon={<CaretRightOutlined />}
              onClick={() => onResume(record)}
            >
              恢复
            </Button>
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
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Select
          allowClear
          placeholder="按优先级筛选"
          style={{ width: 160 }}
          value={priorityFilter}
          onChange={(v) => onPriorityFilterChange(v)}
          options={[
            { value: 'high', label: '优先级：高' },
            { value: 'normal', label: '优先级：普通' },
            { value: 'low', label: '优先级：低' },
          ]}
        />
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
        pagination={{ total, pageSize: 50, showTotal: (t) => `共 ${t} 条任务` }}
      />
    </>
  )
}
