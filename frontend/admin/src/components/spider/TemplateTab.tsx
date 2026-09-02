/**
 * TemplateTab - 任务模板管理（列表 + 运行 + 删除）
 */
import React, { useCallback, useEffect, useState } from 'react'
import {
  Table, Button, Tag, Space, Popconfirm, Empty, Typography, message,
} from 'antd'
import { ReloadOutlined, PlayCircleOutlined, DeleteOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  fetchTemplates, deleteTemplate, runFromTemplate,
} from '../../services/spiders'
import { PRIORITY_META } from './types'
import type { TaskTemplate, Task, SpiderMap } from './types'
import { apiErrorMessage } from '../../utils/errorMessage'

const { Text } = Typography

export interface TemplateTabProps {
  spiderMap: SpiderMap
  canCreate: boolean
  canDelete: boolean
  /** 从模板运行后，回调通知父组件（传递新创建的 task，用于打开日志等） */
  onRunFromTemplate: (task: Task) => void
}

export const TemplateTab: React.FC<TemplateTabProps> = ({
  spiderMap, canCreate, canDelete, onRunFromTemplate,
}) => {
  const [templates, setTemplates] = useState<TaskTemplate[]>([])
  const [loading, setLoading] = useState(false)

  const loadTemplates = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetchTemplates()
      setTemplates(res || [])
    } catch (error) {
      message.error('获取任务模板失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadTemplates()
  }, [loadTemplates])

  const onRun = async (template: TaskTemplate) => {
    try {
      const task = await runFromTemplate(template.id)
      message.success(`任务 #${task.id} 已从模板创建，正在排队执行`)
      onRunFromTemplate(task)
    } catch (error) {
      message.error(apiErrorMessage(error, '创建任务失败'))
    }
  }

  const onDelete = async (template: TaskTemplate) => {
    try {
      await deleteTemplate(template.id)
      message.success(`模板"${template.name}"已删除`)
      loadTemplates()
    } catch (error) {
      message.error(apiErrorMessage(error, '删除失败'))
    }
  }

  const columns: ColumnsType<TaskTemplate> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '模板名称', dataIndex: 'name', key: 'name' },
    {
      title: '爬虫',
      dataIndex: 'spider_name',
      key: 'spider_name',
      render: (name: string) => spiderMap[name]?.title || name,
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
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 180 },
    {
      title: '操作',
      key: 'action',
      width: 180,
      render: (_: unknown, record: TaskTemplate) => (
        <Space size="small">
          {canCreate && (
            <Button
              type="link"
              size="small"
              icon={<PlayCircleOutlined />}
              onClick={() => onRun(record)}
            >
              运行
            </Button>
          )}
          {canDelete && (
            <Popconfirm
              title="确认删除该模板？"
              okText="删除"
              okButtonProps={{ danger: true }}
              cancelText="取消"
              onConfirm={() => onDelete(record)}
            >
              <Button type="link" danger size="small" icon={<DeleteOutlined />}>
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
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          收藏常用任务配置，一键创建任务。从任务列表点击"收藏"按钮即可保存为模板。
        </Text>
        <Button icon={<ReloadOutlined />} onClick={loadTemplates}>刷新</Button>
      </div>
      <Table
        dataSource={templates}
        rowKey="id"
        loading={loading}
        pagination={false}
        locale={{ emptyText: <Empty description={'暂无任务模板，从任务列表点击「收藏」添加'} /> }}
        columns={columns}
      />
    </>
  )
}
