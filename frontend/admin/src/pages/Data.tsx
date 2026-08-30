/**
 * 数据中心页面 - 统计卡片 + 跨任务采集结果检索
 *
 * 能力：
 * - 统计卡片（/admin/stats，ApiResponse 信封需解包 data）
 * - 跨任务结果表格：爬虫/时间范围/关键词筛选，服务端分页（GET /spiders/results）
 * - 行内操作：查看详情（复用 ResultDrawer，按结果所属任务打开）、删除（仅管理员，二次确认）
 * - 导出：按当前筛选条件拉取最多 100 条生成 CSV 下载
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Card, Col, Row, Statistic, Table, Button, Space, Select, Input, DatePicker,
  Tooltip, Typography, message, Popconfirm,
} from 'antd'
import {
  ReloadOutlined, SearchOutlined, DownloadOutlined, DeleteOutlined, EyeOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import api from '../services/api'
import { fetchRegistry, searchResults, deleteResult } from '../services/spiders'
import type { SpiderResult, SpiderInfo } from '../services/spiders'
import { usePermission } from '../hooks/usePermission'
import { ResultDrawer } from '../components/spider/ResultDrawer'
import type { Task, SpiderMap } from '../components/spider/types'

const { Text } = Typography

interface StatsData {
  total_tasks: number
  // /admin/stats 返回平铺状态计数（无 by_status 嵌套），与 Dashboard 同口径
  pending: number
  running: number
  completed: number
  failed: number
}

/** 结果行所属任务的伪对象（ResultDrawer 仅依赖 id/spider_name/status） */
const toPseudoTask = (row: SpiderResult): Task => ({
  id: row.task_id,
  spider_name: row.spider_name,
  status: 'completed',
  priority: 'normal',
  result_count: 0,
})

/** 结果转 CSV（含 BOM，Excel 直接打开不乱码） */
const toCsv = (rows: SpiderResult[]): string => {
  const header = ['id', 'task_id', 'spider_name', 'title', 'content', 'url', 'created_at']
  const esc = (v: unknown) => {
    const s = v === null || v === undefined ? '' : String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const lines = [
    header.join(','),
    ...rows.map((r) => header.map((h) => esc((r as unknown as Record<string, unknown>)[h])).join(',')),
  ]
  return '\ufeff' + lines.join('\n')
}

const Data: React.FC = () => {
  const { hasPermission } = usePermission()
  const canDelete = hasPermission('btn:delete') // 删除结果仅 admin

  // 统计卡片
  const [stats, setStats] = useState<StatsData | null>(null)
  const [statsLoading, setStatsLoading] = useState(true)

  // 爬虫下拉（注册表）
  const [spiders, setSpiders] = useState<SpiderInfo[]>([])
  const spiderMap = useMemo<SpiderMap>(() => {
    const m: SpiderMap = {}
    spiders.forEach((s) => { m[s.name] = { title: s.title, type: s.type } })
    return m
  }, [spiders])

  // 筛选条件
  const [spiderName, setSpiderName] = useState<string | undefined>(undefined)
  const [range, setRange] = useState<any>(null)
  const [keyword, setKeyword] = useState('')

  // 结果表格
  const [rows, setRows] = useState<SpiderResult[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)

  // 详情抽屉（复用 ResultDrawer）
  const [detailTask, setDetailTask] = useState<Task | null>(null)

  const loadStats = useCallback(async () => {
    try {
      // /admin/stats 带 ApiResponse 信封，需解包 data
      const res: any = await api.get('/admin/stats')
      setStats(res.data)
    } catch (error) {
      message.error('获取统计数据失败')
    } finally {
      setStatsLoading(false)
    }
  }, [])

  const buildQuery = useCallback(() => ({
    spider_name: spiderName,
    keyword: keyword.trim() || undefined,
    start_time: range?.[0] ? range[0].format('YYYY-MM-DDTHH:mm:ss') : undefined,
    end_time: range?.[1] ? range[1].format('YYYY-MM-DDTHH:mm:ss') : undefined,
  }), [spiderName, keyword, range])

  const loadResults = useCallback(async (p: number, showSpin = true) => {
    if (showSpin) setLoading(true)
    try {
      const res = await searchResults({ ...buildQuery(), page: p, page_size: 20 })
      setRows(res.items || [])
      setTotal(res.total || 0)
    } catch (error) {
      message.error('获取采集结果失败')
    } finally {
      if (showSpin) setLoading(false)
    }
  }, [buildQuery])

  useEffect(() => {
    loadStats()
    fetchRegistry()
      .then((reg) => setSpiders(reg.spiders || []))
      .catch(() => { /* 下拉为空不阻塞 */ })
    // 挂载时加载第一页结果（筛选变化仍由「查询」按钮触发，避免自动刷新）
    loadResults(1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadStats])

  // 查询条件变化回到第一页
  const onSearch = () => {
    setPage(1)
    loadResults(1)
  }

  const onReset = () => {
    setSpiderName(undefined)
    setRange(null)
    setKeyword('')
    setPage(1)
    // 依赖闭包旧值，直接按空条件拉取（带 loading 态，避免重置期间闪现空态）
    setLoading(true)
    searchResults({ page: 1, page_size: 20 })
      .then((res) => { setRows(res.items || []); setTotal(res.total || 0) })
      .catch(() => message.error('获取采集结果失败'))
      .finally(() => setLoading(false))
  }

  const onDelete = async (row: SpiderResult) => {
    try {
      await deleteResult(row.id)
      message.success(`结果 #${row.id} 已删除`)
      loadResults(page, false)
    } catch (error: any) {
      message.error(error?.response?.data?.message || '删除失败')
    }
  }

  // 按当前筛选条件导出（最多 100 条）
  const onExport = async () => {
    try {
      const res = await searchResults({ ...buildQuery(), page: 1, page_size: 100 })
      const items = res.items || []
      if (!items.length) {
        message.warning('当前筛选条件下没有可导出的数据')
        return
      }
      const blob = new Blob([toCsv(items)], { type: 'text/csv;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `data_center_export_${Date.now()}.csv`
      link.click()
      URL.revokeObjectURL(url)
      message.success(`已导出 ${items.length} 条结果（CSV，当前筛选条件前 100 条）`)
    } catch (error: any) {
      message.error(error?.response?.data?.message || '导出失败')
    }
  }

  const columns: ColumnsType<SpiderResult> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 70 },
    {
      title: '爬虫', dataIndex: 'spider_name', key: 'spider_name', width: 160,
      render: (name: string) => (
        <Space direction="vertical" size={0}>
          <Text strong>{spiderMap[name]?.title || name}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{name}</Text>
        </Space>
      ),
    },
    { title: '所属任务', dataIndex: 'task_id', key: 'task_id', width: 90, render: (v: number) => `#${v}` },
    {
      title: '标题', dataIndex: 'title', key: 'title', width: 220, ellipsis: true,
      render: (v: string | null) => v || '-',
    },
    {
      title: '内容', dataIndex: 'content', key: 'content', ellipsis: true,
      render: (v: string | null) => (v ? <Tooltip title={v}>{v}</Tooltip> : '-'),
    },
    {
      title: 'URL', dataIndex: 'url', key: 'url', width: 180, ellipsis: true,
      render: (v: string | null) => (v ? <a href={v} target="_blank" rel="noreferrer">{v}</a> : '-'),
    },
    { title: '采集时间', dataIndex: 'created_at', key: 'created_at', width: 170 },
    {
      title: '操作', key: 'action', width: 140,
      render: (_: any, record: SpiderResult) => (
        <Space size="small">
          <Button
            type="link" size="small" icon={<EyeOutlined />}
            onClick={() => setDetailTask(toPseudoTask(record))}
          >
            详情
          </Button>
          {canDelete && (
            <Popconfirm
              title="确认删除该条结果？"
              description="删除后不可恢复。"
              okText="删除"
              okButtonProps={{ danger: true }}
              cancelText="取消"
              onConfirm={() => onDelete(record)}
            >
              <Button type="link" danger size="small" icon={<DeleteOutlined />}>删除</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  return (
    <>
      <Row gutter={[16, 16]}>
        <Col span={6}>
          <Card loading={statsLoading}>
            <Statistic title="任务总数" value={stats?.total_tasks ?? 0} />
          </Card>
        </Col>
        <Col span={6}>
          <Card loading={statsLoading}>
            <Statistic title="待执行" value={stats?.pending ?? 0} />
          </Card>
        </Col>
        <Col span={6}>
          <Card loading={statsLoading}>
            <Statistic title="已完成" value={stats?.completed ?? 0} valueStyle={{ color: '#3f8600' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card loading={statsLoading}>
            <Statistic title="失败" value={stats?.failed ?? 0} valueStyle={{ color: '#cf1322' }} />
          </Card>
        </Col>
      </Row>

      <Card title="采集结果检索" style={{ marginTop: 16 }}>
        <Space style={{ marginBottom: 16 }} wrap>
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="按爬虫筛选"
            style={{ width: 240 }}
            value={spiderName}
            onChange={(v) => setSpiderName(v)}
            options={spiders.map((s) => ({ label: `${s.title}（${s.name}）`, value: s.name }))}
          />
          <DatePicker.RangePicker
            showTime
            placeholder={['采集时间起', '采集时间止']}
            value={range}
            onChange={(v) => setRange(v)}
          />
          <Input.Search
            placeholder="关键词（标题/URL/内容）"
            allowClear
            style={{ width: 260 }}
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onSearch={onSearch}
            prefix={<SearchOutlined />}
          />
          <Button type="primary" onClick={onSearch}>查询</Button>
          <Button onClick={onReset}>重置</Button>
          <Button icon={<DownloadOutlined />} onClick={onExport}>导出 CSV</Button>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => { loadStats(); loadResults(page) }}
          >
            刷新
          </Button>
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
            onChange: (p) => { setPage(p); loadResults(p, false) },
            showTotal: (t) => `共 ${t} 条结果`,
          }}
        />
        <div style={{ marginTop: 8 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            「详情」打开该结果所属任务的完整采集结果；导出为当前筛选条件下前 100 条。
          </Text>
        </div>
      </Card>

      {/* 结果详情抽屉（复用任务结果抽屉） */}
      <ResultDrawer task={detailTask} spiderMap={spiderMap} onClose={() => setDetailTask(null)} />
    </>
  )
}

export default Data
