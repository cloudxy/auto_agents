/**
 * AI 采集方案列表（从 pages/AiPlans.tsx 拆出，期 4 前端治理）
 *
 * 自含列表状态：分页 / 状态筛选 / 加载 / 删除刷新；
 * 「继续」按钮经 props.onOpenPlan 上抛给页面（切回向导 tab）。
 */
import React, { useCallback, useEffect, useState } from 'react'
import { Button, Empty, Popconfirm, Select, Space, Table, Tag, Typography, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { DeleteOutlined, EditOutlined, ReloadOutlined } from '@ant-design/icons'
import { AI_PLAN_STATUS_META, AI_PLAN_STATUS_OPTIONS, deleteAiPlan, fetchAiPlans } from '../../services/ai'
import type { AiPlan } from '../../services/ai'
import { apiErrorMessage } from '../../utils/errorMessage'

const { Text } = Typography

interface PlanListProps {
  /** 删除计划权限（仅 admin） */
  canDelete: boolean
  /** 「继续」载入计划到向导（页面注入：同时切回向导 tab） */
  onOpenPlan: (p: AiPlan) => void
}

export const PlanList: React.FC<PlanListProps> = ({ canDelete, onOpenPlan }) => {
  const [plans, setPlans] = useState<AiPlan[]>([])
  const [planTotal, setPlanTotal] = useState(0)
  const [planPage, setPlanPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined)
  const [listLoading, setListLoading] = useState(false)

  const loadPlans = useCallback(async (showSpin = true) => {
    if (showSpin) setListLoading(true)
    try {
      const res = await fetchAiPlans({ skip: (planPage - 1) * 20, limit: 20, status: statusFilter })
      setPlans(res.items || [])
      setPlanTotal(res.total || 0)
    } catch (error) {
      message.error(apiErrorMessage(error, '获取 AI 方案列表失败'))
    } finally {
      if (showSpin) setListLoading(false)
    }
  }, [planPage, statusFilter])

  useEffect(() => {
    loadPlans()
  }, [loadPlans])

  const onDeletePlan = async (p: AiPlan) => {
    try {
      await deleteAiPlan(p.id)
      message.success(`计划 #${p.id} 已删除`)
      loadPlans(false)
    } catch (error) {
      message.error(apiErrorMessage(error, '删除失败'))
    }
  }

  // ---------------- 方案列表列 ----------------
  const planColumns: ColumnsType<AiPlan> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 70 },
    {
      title: '目标链接', dataIndex: 'target_url', key: 'target_url', ellipsis: true,
      render: (v: string) => <a href={v} target="_blank" rel="noreferrer">{v}</a>,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 110,
      render: (status: string) => {
        const meta = AI_PLAN_STATUS_META[status] || { label: status, color: 'default' }
        return <Tag color={meta.color}>{meta.label}</Tag>
      },
    },
    { title: '修复迭代', dataIndex: 'iteration_count', key: 'iteration_count', width: 90, align: 'center' },
    {
      title: '试采任务', dataIndex: 'test_task_id', key: 'test_task_id', width: 90,
      render: (v: number | null) => (v ? `#${v}` : '-'),
    },
    {
      title: '注册定义', key: 'registered', width: 180, ellipsis: true,
      render: (_: unknown, record: AiPlan) => (
        record.plan_json?.registered_definition
          ? <Text code style={{ fontSize: 12 }}>{record.plan_json.registered_definition}</Text>
          : '-'
      ),
    },
    { title: '创建人', dataIndex: 'created_by', key: 'created_by', width: 100, render: (v: string | null) => v || '-' },
    { title: '更新时间', dataIndex: 'updated_at', key: 'updated_at', width: 170, render: (v: string | null) => v || '-' },
    {
      title: '操作', key: 'action', width: 150,
      render: (_: unknown, record: AiPlan) => (
        <Space size="small">
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => onOpenPlan(record)}>
            继续
          </Button>
          {canDelete && (
            <Popconfirm
              title="确认删除该计划？"
              description="规划/试采进行中时后端将拒绝删除。"
              okText="删除"
              okButtonProps={{ danger: true }}
              cancelText="取消"
              onConfirm={() => onDeletePlan(record)}
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
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Select
          allowClear
          placeholder="按状态筛选"
          style={{ width: 160 }}
          value={statusFilter}
          onChange={(v) => { setPlanPage(1); setStatusFilter(v) }}
          options={AI_PLAN_STATUS_OPTIONS}
        />
        <Button icon={<ReloadOutlined />} onClick={() => loadPlans()}>刷新</Button>
      </div>
      <Table
        columns={planColumns}
        dataSource={plans}
        rowKey="id"
        loading={listLoading}
        pagination={{
          current: planPage,
          pageSize: 20,
          total: planTotal,
          onChange: setPlanPage,
          showTotal: (t) => `共 ${t} 个计划`,
        }}
        locale={{ emptyText: <Empty description="暂无 AI 采集计划，去「采集向导」创建一个" /> }}
      />
    </>
  )
}

export default PlanList
