/**
 * ResultDrawer - 结果查看抽屉（表格 + 导出 + 存储信息）
 */
import React, { useEffect, useState } from 'react'
import { Drawer, Table, Button, Space, Tag, Tooltip, Typography, message } from 'antd'
import { DownloadOutlined } from '@ant-design/icons'
import { fetchResults, exportResults, fetchTaskStore } from '../../services/spiders'
import type { Task, SpiderResult, TaskStoreStatus, SpiderMap } from './types'

const { Text } = Typography

export interface ResultDrawerProps {
  task: Task | null
  spiderMap: SpiderMap
  onClose: () => void
}

export const ResultDrawer: React.FC<ResultDrawerProps> = ({ task, spiderMap, onClose }) => {
  const [results, setResults] = useState<SpiderResult[]>([])
  const [resultTotal, setResultTotal] = useState(0)
  const [resultPage, setResultPage] = useState(1)
  const [resultLoading, setResultLoading] = useState(false)
  const [storeInfo, setStoreInfo] = useState<TaskStoreStatus | null>(null)
  // 已同步重置过列表态的任务 ID（渲染期调整 state：打开/切换抽屉首帧即进入 loading，避免闪现「No data」空态）
  const [loadedTaskId, setLoadedTaskId] = useState<number | null>(null)
  const activeTaskId = task?.id ?? null
  if (activeTaskId !== loadedTaskId) {
    setLoadedTaskId(activeTaskId)
    setResults([])
    setResultTotal(0)
    setResultPage(1)
    setResultLoading(!!task)
  }

  useEffect(() => {
    if (!task) return
    setResultLoading(true)
    fetchResults(task.id, (resultPage - 1) * 20, 20)
      .then((res) => {
        setResults(res.items || [])
        setResultTotal(res.total || 0)
      })
      .catch(() => message.error('获取采集结果失败'))
      .finally(() => setResultLoading(false))
  }, [task, resultPage])

  // 拉取存储目标状态
  useEffect(() => {
    if (!task) {
      setStoreInfo(null)
      return
    }
    fetchTaskStore(task.id).then(setStoreInfo).catch(() => { /* 静默失败 */ })
  }, [task])

  const onExport = async (format: 'csv' | 'json') => {
    if (!task) return
    try {
      const blob = await exportResults(task.id, format)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `task_${task.id}.${format}`
      link.click()
      URL.revokeObjectURL(url)
      message.success(`已导出任务 #${task.id} 的结果（${format.toUpperCase()}）`)
    } catch (error: any) {
      message.error(error?.response?.data?.message || '导出失败')
    }
  }

  const handleClose = () => {
    setResultPage(1)
    setResults([])
    setResultTotal(0)
    setStoreInfo(null)
    onClose()
  }

  const columns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 70 },
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      width: 220,
      ellipsis: true,
      render: (v: string | null) => v || '-',
    },
    {
      title: '内容',
      dataIndex: 'content',
      key: 'content',
      ellipsis: true,
      render: (v: string | null) => (v ? <Tooltip title={v}>{v}</Tooltip> : '-'),
    },
    {
      title: 'URL',
      dataIndex: 'url',
      key: 'url',
      width: 180,
      ellipsis: true,
      render: (v: string | null) =>
        v ? <a href={v} target="_blank" rel="noreferrer">{v}</a> : '-',
    },
    { title: '采集时间', dataIndex: 'created_at', key: 'created_at', width: 170 },
    {
      title: '内容指纹',
      dataIndex: 'content_hash',
      key: 'content_hash',
      width: 110,
      render: (v: string | null) => v ? <Tooltip title={v}><Text code style={{ fontSize: 11 }}>{v.slice(0, 8)}</Text></Tooltip> : '-',
    },
  ]

  return (
    <Drawer
      title={
        <Space>
          采集结果
          {task && (
            <Text type="secondary">
              #{task.id} {spiderMap[task.spider_name]?.title || task.spider_name}
              （共 {resultTotal} 条）
            </Text>
          )}
        </Space>
      }
      open={!!task}
      onClose={handleClose}
      width={860}
      footer={
        <Space style={{ float: 'right' }}>
          <Button icon={<DownloadOutlined />} onClick={() => onExport('csv')}>导出 CSV</Button>
          <Button icon={<DownloadOutlined />} onClick={() => onExport('json')}>导出 JSON</Button>
        </Space>
      }
    >
      {storeInfo && storeInfo.targets.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <Space wrap>
            <Text type="secondary">额外存储：</Text>
            {storeInfo.targets.map((t) => <Tag key={t} color={t === 'csv' ? 'orange' : 'geekblue'}>{t}</Tag>)}
            {typeof storeInfo.redis_count === 'number' && (
              <Text type="secondary">缓存 {storeInfo.redis_count} 条</Text>
            )}
            {storeInfo.csv_path && (
              <Text type="secondary" style={{ fontSize: 12 }}>csv：{storeInfo.csv_path}</Text>
            )}
          </Space>
        </div>
      )}
      <Table
        dataSource={results}
        rowKey="id"
        loading={resultLoading}
        size="small"
        pagination={{
          current: resultPage,
          pageSize: 20,
          total: resultTotal,
          onChange: setResultPage,
          showTotal: (t) => `共 ${t} 条结果`,
        }}
        columns={columns}
      />
    </Drawer>
  )
}
