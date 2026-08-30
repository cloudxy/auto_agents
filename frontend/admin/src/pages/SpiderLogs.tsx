/**
 * 爬虫运行日志页面 - 选择任务查看 Worker 实时日志
 * 支持全文关键词搜索和日志级别过滤
 */
import React, { useEffect, useRef, useState } from 'react'
import { Card, Select, Space, Tag, Empty, Button, Typography, Input } from 'antd'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import { fetchTaskLogs, Task, TaskLogResponse } from '../services/spiders'

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
  const [tasks, setTasks] = useState<Task[]>([])
  const [taskId, setTaskId] = useState<number | null>(null)
  const [logData, setLogData] = useState<TaskLogResponse | null>(null)
  const [keyword, setKeyword] = useState<string>('')
  const [level, setLevel] = useState<string>('')
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    import('../services/spiders').then(({ fetchTasks }) =>
      fetchTasks(0, 50)
        .then((res) => {
          setTasks(res.items || [])
          if (res.items?.length && taskId === null) {
            setTaskId(res.items[0].id)
          }
        })
        .catch(() => setTasks([]))
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 选中任务后轮询日志（未终态 2 秒一次）
  useEffect(() => {
    if (!taskId) return
    const pull = () => {
      fetchTaskLogs(taskId, 200, keyword || undefined, level || undefined)
        .then((data) => {
          setLogData(data)
          // 终态后停止轮询
          if (data.status === 'completed' || data.status === 'failed') {
            if (timer.current) {
              clearInterval(timer.current)
              timer.current = null
            }
          }
        })
        .catch(() => { /* 轮询静默失败 */ })
    }
    pull()
    if (!timer.current) {
      timer.current = setInterval(pull, 2000)
    }
    return () => {
      if (timer.current) {
        clearInterval(timer.current)
        timer.current = null
      }
    }
  }, [taskId, keyword, level])

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
            value={taskId}
            onChange={setTaskId}
            options={tasks.map((t) => ({
              label: `#${t.id} ${t.spider_name}（${STATUS_META[t.status]?.label || t.status}）`,
              value: t.id,
            }))}
          />
          {meta && <Tag color={meta.color}>{meta.label}</Tag>}
          <Button
            icon={<ReloadOutlined />}
            onClick={() => taskId && fetchTaskLogs(taskId, 200, keyword || undefined, level || undefined).then(setLogData).catch(() => {})}
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
