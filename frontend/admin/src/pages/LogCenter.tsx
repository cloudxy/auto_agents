/**
 * 日志中心页面 - 任务日志 + 审计日志
 *
 * - 任务日志：直接复用现有 SpiderLogs 页组件（任务选择 + 关键词/级别过滤 + 2s 轮询）
 * - 审计日志：对接 GET /admin/audit-logs（ApiResponse 信封需解包 data），
 *   操作人/操作类型/时间范围筛选，仅管理员可见（后端为最终防线）
 */
import React, { useCallback, useEffect, useState } from 'react'
import {
  Card, Tabs, Table, Tag, Space, Input, Button, DatePicker, Typography, message, Alert,
} from 'antd'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import api from '../services/api'
import SpiderLogs from './SpiderLogs'
import { usePermission } from '../hooks/usePermission'
import type { Dayjs } from 'dayjs'

const { Text } = Typography

/** RangePicker 值契约（antd 泛型缺失场景的手写对齐） */
type RangeValue = [Dayjs | null, Dayjs | null] | null

interface AuditLogItem {
  id: number
  actor_id?: number | null
  actor_name: string
  action: string
  target: string
  detail?: string | null
  created_at?: string | null
}

/** 审计日志页签（仅管理员可见数据） */
const AuditLogsTab: React.FC = () => {
  const { isAdmin } = usePermission()
  const [rows, setRows] = useState<AuditLogItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [userFilter, setUserFilter] = useState('')
  const [actionFilter, setActionFilter] = useState('')
  const [range, setRange] = useState<RangeValue>(null)

  const buildQuery = useCallback(() => ({
    user: userFilter.trim() || undefined,
    action: actionFilter.trim() || undefined,
    start_time: range?.[0] ? range[0].format('YYYY-MM-DDTHH:mm:ss') : undefined,
    end_time: range?.[1] ? range[1].format('YYYY-MM-DDTHH:mm:ss') : undefined,
  }), [userFilter, actionFilter, range])

  const loadLogs = useCallback(async (p: number, showSpin = true) => {
    if (!isAdmin) return
    if (showSpin) setLoading(true)
    try {
      // /admin/audit-logs 带 ApiResponse 信封，需解包 data
      const res = await api.get<{ items: AuditLogItem[]; total: number }>('/admin/audit-logs', {
        params: { skip: (p - 1) * 20, limit: 20, ...buildQuery() },
      })
      setRows(res.data?.items || [])
      setTotal(res.data?.total || 0)
    } catch (error) {
      message.error('获取审计日志失败')
    } finally {
      if (showSpin) setLoading(false)
    }
  }, [isAdmin, buildQuery])

  useEffect(() => {
    loadLogs(page)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, isAdmin])

  const onSearch = () => {
    setPage(1)
    loadLogs(1)
  }

  const columns: ColumnsType<AuditLogItem> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 70 },
    { title: '操作人', dataIndex: 'actor_name', key: 'actor_name', width: 120 },
    {
      title: '操作类型', dataIndex: 'action', key: 'action', width: 180,
      render: (v: string) => <Tag color="blue"><Text code style={{ fontSize: 12 }}>{v}</Text></Tag>,
    },
    { title: '操作对象', dataIndex: 'target', key: 'target', width: 180, ellipsis: true },
    {
      title: '详情', dataIndex: 'detail', key: 'detail', ellipsis: true,
      render: (v: string | null) => (v ? <Text code style={{ fontSize: 12 }}>{v}</Text> : '-'),
    },
    { title: '操作时间', dataIndex: 'created_at', key: 'created_at', width: 180 },
  ]

  if (!isAdmin) {
    return <Alert type="warning" showIcon title="审计日志仅管理员可查看" />
  }

  return (
    <>
      <Space style={{ marginBottom: 16 }} wrap>
        <Input
          allowClear
          placeholder="操作人用户名"
          style={{ width: 180 }}
          value={userFilter}
          onChange={(e) => setUserFilter(e.target.value)}
          onPressEnter={onSearch}
          prefix={<SearchOutlined />}
        />
        <Input
          allowClear
          placeholder="操作类型，如 task.run"
          style={{ width: 200 }}
          value={actionFilter}
          onChange={(e) => setActionFilter(e.target.value)}
          onPressEnter={onSearch}
        />
        <DatePicker.RangePicker
          showTime
          placeholder={['操作时间起', '操作时间止']}
          value={range}
          onChange={(v) => setRange(v)}
        />
        <Button type="primary" onClick={onSearch}>查询</Button>
        <Button
          onClick={() => { setUserFilter(''); setActionFilter(''); setRange(null); setPage(1); loadLogs(1) }}
        >
          重置
        </Button>
        <Button icon={<ReloadOutlined />} onClick={() => loadLogs(page)}>刷新</Button>
      </Space>
      <Table
        columns={columns}
        dataSource={rows}
        rowKey="id"
        loading={loading}
        pagination={{
          current: page,
          pageSize: 20,
          total,
          onChange: (p) => setPage(p),
          showTotal: (t) => `共 ${t} 条审计记录`,
        }}
      />
    </>
  )
}

const LogCenter: React.FC = () => (
  <Card title="日志中心">
    <Tabs
      items={[
        {
          key: 'task',
          label: '任务日志',
          children: <SpiderLogs />,
        },
        {
          key: 'audit',
          label: '审计日志',
          children: <AuditLogsTab />,
        },
      ]}
    />
  </Card>
)

export default LogCenter
