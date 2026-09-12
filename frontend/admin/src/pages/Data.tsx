/**
 * 数据中心页面 - 统计卡片 + 跨任务采集结果检索
 *
 * 能力：
 * - 统计卡片（/admin/stats，ApiResponse 信封需解包 data）
 * - 跨任务结果表格：爬虫/时间范围/关键词筛选，服务端分页（GET /spiders/results）
 * - 行内操作：查看详情（复用 ResultDrawer，按结果所属任务打开）、删除（仅管理员，二次确认）
 * - 导出：按当前筛选条件拉取最多 100 条非候选，格式仅 CSV/JSON（无 xlsx）
 */
import React, { useCallback, useMemo, useState } from 'react'
import {
  Card, Col, Row, Statistic, Table, Button, Space, Select, Input, DatePicker,
  Tooltip, Typography, message, Popconfirm,
} from 'antd'
import {
  ReloadOutlined, SearchOutlined, DownloadOutlined, DeleteOutlined, EyeOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { fetchRegistry, searchResults, deleteResult } from '../services/spiders'
import type { SpiderResult, SpiderInfo } from '../services/spiders'
import { usePermission } from '../hooks/usePermission'
import { ResultDrawer } from '../components/spider/ResultDrawer'
import { LoadEmpty, LoadFailure } from '../components/LoadState'
import type { Task, SpiderMap } from '../components/spider/types'
import { apiErrorMessage } from '../utils/errorMessage'
import type { Dayjs } from 'dayjs'
import { fetchAdminStats } from '../services/admin'

const { Text } = Typography

/** RangePicker 值契约（antd 泛型缺失场景的手写对齐） */
type RangeValue = [Dayjs | null, Dayjs | null] | null

// T-17 / FR-84：失败≠空——失败句+重试；真 0 走「还没有…」+ 去采集；统计卡失败不得 ?? 0
const STATS_LOAD_FAILED = '统计数据加载失败。检查网络后重试。'
const RESULTS_LOAD_FAILED = '结果加载失败。检查网络后重试。'
const EMPTY_RESULTS = '还没有采集结果。完成一次采集后会显示在这里。'

/** 已提交检索条件（草稿筛选只在点「查询/重置/翻页」时落到这里） */
interface AppliedQuery {
  page: number
  spider_name?: string
  keyword?: string
  start_time?: string
  end_time?: string
}

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
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // react-query 托管读模型：isError/refetch 驱动 FR-84 失败态；统计卡失败不落 0
  const statsQuery = useQuery({
    queryKey: ['data-stats'],
    queryFn: () => fetchAdminStats<StatsData>(),
  })
  const stats = statsQuery.data ?? null

  // 爬虫下拉（注册表）；失败不阻塞（下拉为空可手填关键词检索）
  const registryQuery = useQuery({ queryKey: ['spider-registry'], queryFn: fetchRegistry })
  const spiders: SpiderInfo[] = useMemo(
    () => registryQuery.data?.spiders || [],
    [registryQuery.data],
  )
  const spiderMap = useMemo<SpiderMap>(() => {
    const m: SpiderMap = {}
    spiders.forEach((s) => { m[s.name] = { title: s.title, type: s.type } })
    return m
  }, [spiders])

  // 筛选条件（草稿）：只在点「查询/重置/翻页」时提交到 applied
  const [spiderName, setSpiderName] = useState<string | undefined>(undefined)
  const [range, setRange] = useState<RangeValue>(null)
  const [keyword, setKeyword] = useState('')
  const [applied, setApplied] = useState<AppliedQuery>({ page: 1 })

  // 结果表格（已提交条件 = 查询键；换页/换筛选保留旧表，不闪空态）
  const resultsQuery = useQuery({
    queryKey: ['data-results', applied],
    queryFn: () => searchResults({ ...applied, page_size: 20 }),
    placeholderData: (prev) => prev,
  })
  const rows = resultsQuery.data?.items || []
  const total = resultsQuery.data?.total || 0

  // 详情抽屉（复用 ResultDrawer）
  const [detailTask, setDetailTask] = useState<Task | null>(null)
  const [exportFmt, setExportFmt] = useState<'csv' | 'json'>('csv')
  const [exporting, setExporting] = useState(false)

  const buildQuery = useCallback(() => ({
    spider_name: spiderName,
    keyword: keyword.trim() || undefined,
    start_time: range?.[0] ? range[0].format('YYYY-MM-DDTHH:mm:ss') : undefined,
    end_time: range?.[1] ? range[1].format('YYYY-MM-DDTHH:mm:ss') : undefined,
  }), [spiderName, keyword, range])

  // 查询条件变化回到第一页；同键重复点也真拉一次（保持按钮语义）
  const onSearch = () => {
    setApplied({ ...buildQuery(), page: 1 })
    queryClient.invalidateQueries({ queryKey: ['data-results'] })
  }

  const onReset = () => {
    setSpiderName(undefined)
    setRange(null)
    setKeyword('')
    setApplied({ page: 1 })
    queryClient.invalidateQueries({ queryKey: ['data-results'] })
  }

  const onDelete = async (row: SpiderResult) => {
    try {
      await deleteResult(row.id)
      message.success(`结果 #${row.id} 已删除`)
      queryClient.invalidateQueries({ queryKey: ['data-results'] })
    } catch (error) {
      message.error(apiErrorMessage(error, '删除失败'))
    }
  }

  // 按当前筛选条件导出（最多 100 条非候选；空窗不下载）
  const onExport = async () => {
    setExporting(true)
    try {
      const res = await searchResults({ ...buildQuery(), page: 1, page_size: 100 })
      const items = (res.items || [])
        .filter((r) => r.source !== 'marketplace')
        .slice(0, 100)
      if (!items.length) {
        message.warning('没有可导出的结果')
        return
      }
      const isJson = exportFmt === 'json'
      const blob = new Blob(
        [isJson ? JSON.stringify(items, null, 2) : toCsv(items)],
        { type: isJson ? 'application/json' : 'text/csv;charset=utf-8' },
      )
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `data_center_export_${Date.now()}.${exportFmt}`
      link.click()
      URL.revokeObjectURL(url)
      message.success(`已导出 ${items.length} 条结果（${exportFmt.toUpperCase()}）`)
    } catch (error) {
      message.error(apiErrorMessage(error, '导出失败。检查网络后重试。'))
    } finally {
      setExporting(false)
    }
  }

  const columns: ColumnsType<SpiderResult> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 70 },
    {
      title: '采集方案', dataIndex: 'spider_name', key: 'spider_name', width: 160,
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
      render: (_: unknown, record: SpiderResult) => (
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
      {/* GWT-84.1：统计卡加载失败=失败句+重试（卡片区替换，不得用 0 冒充）；检索区照常工作 */}
      {statsQuery.isError ? (
        <LoadFailure title={STATS_LOAD_FAILED} onRetry={() => statsQuery.refetch()} />
      ) : (
      <Row gutter={[16, 16]}>
        <Col span={6}>
          <Card loading={statsQuery.isPending}>
            <Statistic title="任务总数" value={stats?.total_tasks ?? 0} />
          </Card>
        </Col>
        <Col span={6}>
          <Card loading={statsQuery.isPending}>
            <Statistic title="待执行" value={stats?.pending ?? 0} />
          </Card>
        </Col>
        <Col span={6}>
          <Card loading={statsQuery.isPending}>
            <Statistic title="已完成" value={stats?.completed ?? 0} valueStyle={{ color: '#3f8600' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card loading={statsQuery.isPending}>
            <Statistic title="失败" value={stats?.failed ?? 0} valueStyle={{ color: '#cf1322' }} />
          </Card>
        </Col>
      </Row>
      )}

      <Card title="采集结果检索" style={{ marginTop: 16 }}>
        <Space style={{ marginBottom: 16 }} wrap>
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="按采集方案筛选"
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
          <Select
            value={exportFmt}
            onChange={(v) => setExportFmt(v)}
            style={{ width: 110 }}
            options={[
              { label: 'CSV', value: 'csv' },
              { label: 'JSON', value: 'json' },
            ]}
            aria-label="导出格式"
          />
          <Button icon={<DownloadOutlined />} onClick={onExport} loading={exporting}>
            {exporting ? '导出中…' : '导出'}
          </Button>
          <Text type="secondary">单次最多 100 条</Text>
          <Button
            icon={<ReloadOutlined />}
            loading={statsQuery.isFetching || resultsQuery.isFetching}
            onClick={() => { statsQuery.refetch(); resultsQuery.refetch() }}
          >
            刷新
          </Button>
        </Space>
        {/* GWT-84.1：结果加载失败=失败句+重试（无旧数据时整表替换，不落「暂无数据」；
            有旧数据时句置顶、旧表保留）；GWT-84.2 真 0=「还没有…」+ 去采集 */}
        {resultsQuery.isError && rows.length === 0 ? (
          <LoadFailure title={RESULTS_LOAD_FAILED} onRetry={() => resultsQuery.refetch()} />
        ) : (
          <>
            {resultsQuery.isError && (
              <LoadFailure style={{ marginBottom: 12 }} title={RESULTS_LOAD_FAILED} onRetry={() => resultsQuery.refetch()} />
            )}
            <Table
              columns={columns}
              dataSource={rows}
              rowKey="id"
              loading={resultsQuery.isPending}
              pagination={{
                current: applied.page,
                pageSize: 20,
                total,
                onChange: (p) => setApplied((a) => ({ ...a, page: p })),
                showTotal: (t) => `共 ${t} 条结果`,
              }}
              locale={{
                emptyText: (
                  <LoadEmpty
                    title={EMPTY_RESULTS}
                    action={<Button type="primary" size="small" onClick={() => navigate('/spiders/tasks')}>去采集</Button>}
                  />
                ),
              }}
            />
          </>
        )}
        <div style={{ marginTop: 8 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            「详情」打开该结果所属任务的完整采集结果。导出仅 CSV 或 JSON，单次最多 100 条。
          </Text>
        </div>
      </Card>

      {/* 结果详情抽屉（复用任务结果抽屉） */}
      <ResultDrawer task={detailTask} spiderMap={spiderMap} onClose={() => setDetailTask(null)} />
    </>
  )
}

export default Data
