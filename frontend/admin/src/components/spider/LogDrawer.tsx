/**
 * LogDrawer - 日志查看抽屉（轮询 + 搜索 + 级别筛选）
 */
import React, { useEffect, useRef, useState } from 'react'
import { Drawer, Input, Select, Space, Tag, Typography, Empty } from 'antd'
import { fetchTaskLogs } from '../../services/spiders'
import { STATUS_META } from './types'
import type { Task, TaskLogResponse, SpiderMap } from './types'

const { Text } = Typography

export interface LogDrawerProps {
  task: Task | null
  spiderMap: SpiderMap
  onClose: () => void
}

export const LogDrawer: React.FC<LogDrawerProps> = ({ task, spiderMap, onClose }) => {
  const [logData, setLogData] = useState<TaskLogResponse | null>(null)
  const [logKeyword, setLogKeyword] = useState<string>('')
  const [logLevel, setLogLevel] = useState<string>('')
  const logTimer = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!task) return
    const pull = () => {
      fetchTaskLogs(task.id, 200, logKeyword || undefined, logLevel || undefined)
        .then(setLogData)
        .catch(() => { /* 轮询静默失败 */ })
    }
    pull()
    logTimer.current = setInterval(pull, 2000)
    return () => {
      if (logTimer.current) clearInterval(logTimer.current)
      logTimer.current = null
    }
  }, [task, logKeyword, logLevel])

  const handleClose = () => {
    setLogData(null)
    setLogKeyword('')
    setLogLevel('')
    onClose()
  }

  const logStatus = logData?.status || task?.status
  const logMeta = logStatus ? STATUS_META[logStatus] : null

  return (
    <Drawer
      title={
        <Space>
          运行日志
          {task && <Text type="secondary">#{task.id} {spiderMap[task.spider_name]?.title || task.spider_name}</Text>}
          {logMeta && <Tag color={logMeta.color}>{logMeta.label}</Tag>}
        </Space>
      }
      open={!!task}
      onClose={handleClose}
      width={720}
    >
      <Space style={{ marginBottom: 12 }} wrap>
        <Input.Search
          placeholder="搜索日志关键词"
          allowClear
          onSearch={(v) => setLogKeyword(v)}
          style={{ width: 220 }}
        />
        <Select
          style={{ width: 130 }}
          value={logLevel}
          onChange={(v) => setLogLevel(v)}
          options={[
            { label: '全部级别', value: '' },
            { label: 'DEBUG', value: 'DEBUG' },
            { label: 'INFO', value: 'INFO' },
            { label: 'WARNING', value: 'WARNING' },
            { label: 'ERROR', value: 'ERROR' },
            { label: 'CRITICAL', value: 'CRITICAL' },
          ]}
          placeholder="日志级别"
        />
      </Space>
      {logData && logData.lines.length > 0 ? (
        <pre
          style={{
            background: '#0d1117', color: '#c9d1d9', padding: 16, borderRadius: 8,
            fontSize: 12, lineHeight: 1.6, minHeight: 300, maxHeight: '70vh',
            overflow: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-all',
          }}
        >
          {logData.lines.join('\n')}
        </pre>
      ) : (
        <Empty description="暂无日志输出（Worker 启动后开始记录）" />
      )}
      <div style={{ marginTop: 8 }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          日志每 2 秒自动刷新（按任务隔离）；任务状态：{logStatus || '-'}
          {logKeyword && <span> · 关键词：「{logKeyword}」</span>}
          {logLevel && <span> · 级别：{logLevel}</span>}
        </Text>
      </div>
    </Drawer>
  )
}
