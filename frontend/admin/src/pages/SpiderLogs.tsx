/**
 * 爬虫运行日志页面 - 选择任务查看 Worker 实时日志
 * 支持全文关键词搜索和日志级别过滤
 */
import React, { useState } from 'react'
import { Card, Select, Space, Tag, Empty, Button, Typography, Input } from 'antd'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import { fetchTaskLogs, fetchTasks, Task } from '../services/spiders'
import { useQuery } from '@tanstack/react-query'

const { Text } = Typography

const STATUS_META: Record<string, { label: string; color: string }> = {
  pending: { label: '待执行', color: 'gold' },
  running: { label: '运行中', color: 'processing' },
  completed: { label: '已完成', color: 'green' },
  failed: { label: '失败', color: 'red' },
}

const LOG_LEVELS = [
  { label: '全部级别', value: '' },
  { label: 'DEBUG', value: 'DEBUG' },
  { label: 'INFO', value: 'INFO' },
  { label: 'WARNING', value: 'WARNING' },
  { label: 'ERROR', value: 'ERROR' },
  { label: 'CRITICAL', value: 'CRITICAL' },
]

const SpiderLogs: React.FC = () => {
  const [taskId, setTaskId] = useState<number | null>(null)
  const [keyword, setKeyword] = useState<string>('')
  const [level, setLevel] = useState<string>('')
  const tasksQ = useQuery({
    queryKey: ['spider-tasks', 'logs-picker'],
    queryFn: () => fetchTasks(0, 50),
  })
  const tasks: Task[] = tasksQ.data?.items ?? []
  const effectiveTaskId = taskId ?? tasks[0]?.id ?? null

  // 工单 78：日志轮询交 react-query（2s 一次，终态自动停——refetchInterval 按数据判定）
  const { data: logData, refetch: refetchLogs } = useQuery({
    queryKey: ['task-logs', effectiveTaskId, keyword, level],
    queryFn: () => fetchTaskLogs(effectiveTaskId!, 200, keyword || undefined, level || undefined),
    enabled: !!effectiveTaskId,
    refetchInterval: (query) => {
      const s = query.state.data?.status
      return s === 'completed' || s === 'failed' ? false : 2000
    },
  })

  const status = logData?.status
  const meta = status ? STATUS_META[status] : null

  const handleSearch = (value: string) => {
    setKeyword(value)
  }

  const handleLevelChange = (value: string) => {
    setLevel(value)
  }

  return (
    <Card
      title="运行日志"
      extra={
        <Space>
          <Select
            style={{ width: 240 }}
            placeholder="选择任务"
            value={effectiveTaskId}
            onChange={setTaskId}
            options={tasks.map((t) => ({
              label: `#${t.id} ${t.spider_name}（${STATUS_META[t.status]?.label || t.status}）`,
              value: t.id,
            }))}
          />
          {meta && <Tag color={meta.color}>{meta.label}</Tag>}
          <Button
            icon={<ReloadOutlined />}
            onClick={() => refetchLogs()}
          >
            刷新
          </Button>
        </Space>
      }
    >
      <Space style={{ marginBottom: 12 }} wrap>
        <Input.Search
          placeholder="搜索日志关键词"
          allowClear
          onSearch={handleSearch}
          style={{ width: 260 }}
          prefix={<SearchOutlined />}
        />
        <Select
          style={{ width: 140 }}
          value={level}
          onChange={handleLevelChange}
          options={LOG_LEVELS}
          placeholder="日志级别"
        />
      </Space>
      {logData && logData.lines.length > 0 ? (
        <pre
          style={{
            background: '#0d1117', color: '#c9d1d9', padding: 16, borderRadius: 8,
            fontSize: 12, lineHeight: 1.6, minHeight: 400, maxHeight: '70vh',
            overflow: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-all',
          }}
        >
          {logData.lines.join('\n')}
        </pre>
      ) : (
        <Empty description="暂无日志输出（任务运行后开始记录）" />
      )}
      <div style={{ marginTop: 8 }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          未终态任务的日志每 2 秒自动刷新
          {keyword && <span> · 关键词：「{keyword}」</span>}
          {level && <span> · 级别：{level}</span>}
        </Text>
      </div>
    </Card>
  )
}

export default SpiderLogs
