/**
 * Worker 节点页面（阶段 2.2）
 *
 * 数据源：/spiders/nodes（Redis 心跳键扫描）
 * 展示：在线状态、进程信息、承载爬虫、各爬虫当前活跃任务
 */
import React, { useCallback, useEffect, useState } from 'react'
import { Card, Table, Tag, Button, Space, message, Badge, Typography, Empty } from 'antd'
import { ClusterOutlined, ReloadOutlined } from '@ant-design/icons'
import api from '../services/api'

const { Text } = Typography

interface ActiveTask {
  spider_name: string
  task_id: number | null
  status: string | null
}

interface WorkerNode {
  worker_id: string
  pid: number | null
  spiders: string[]
  started_at: string | null
  respawn_count: number
  online: boolean
  active_tasks: ActiveTask[]
}

const Nodes: React.FC = () => {
  const [loading, setLoading] = useState(false)
  const [nodes, setNodes] = useState<WorkerNode[]>([])
  const [total, setTotal] = useState(0)

  const loadNodes = useCallback(async (showSpin = true) => {
    if (showSpin) setLoading(true)
    try {
      const res = await api.get<{ items: WorkerNode[]; total: number }>('/spiders/nodes')
      // /spiders/nodes 带 ApiResponse 信封（ADR-001），需解包 data
      setNodes(res.data?.items || [])
      setTotal(res.data?.total || 0)
    } catch (error) {
      message.error('获取节点列表失败')
    } finally {
      if (showSpin) setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadNodes()
    // 心跳 10s 续约一次，15s 轮询即可跟上离线判定
    const timer = setInterval(() => loadNodes(false), 15000)
    return () => clearInterval(timer)
  }, [loadNodes])

  const columns = [
    {
      title: '状态',
      key: 'online',
      width: 90,
      render: (_: unknown, record: WorkerNode) =>
        record.online
          ? <Badge status="success" text="在线" />
          : <Badge status="error" text="离线" />,
    },
    {
      title: '节点',
      key: 'worker_id',
      render: (_: unknown, record: WorkerNode) => (
        <Space direction="vertical" size={0}>
          <Text strong><ClusterOutlined style={{ marginRight: 6 }} />{record.worker_id}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            PID {record.pid ?? '-'} · 启动于 {record.started_at || '-'} · 重启 {record.respawn_count} 次
          </Text>
        </Space>
      ),
    },
    {
      title: '承载爬虫',
      key: 'spiders',
      render: (_: unknown, record: WorkerNode) =>
        record.spiders.length
          ? record.spiders.map((s) => <Tag key={s} color="cyan">{s}</Tag>)
          : <Text type="secondary">-</Text>,
    },
    {
      title: '当前任务',
      key: 'active_tasks',
      render: (_: unknown, record: WorkerNode) => {
        const running = record.active_tasks.filter((t) => t.task_id)
        if (!running.length) return <Text type="secondary">空闲</Text>
        return running.map((t) => (
          <Tag key={t.spider_name} color={t.status === 'running' ? 'processing' : 'default'}>
            {t.spider_name} #{t.task_id}
          </Tag>
        ))
      },
    },
  ]

  return (
    <Card
      title={<span><ClusterOutlined style={{ marginRight: 8 }} />Worker 节点（共 {total} 个）</span>}
      extra={<Button icon={<ReloadOutlined />} onClick={() => loadNodes()}>刷新</Button>}
    >
      <Table
        columns={columns}
        dataSource={nodes}
        rowKey="worker_id"
        loading={loading}
        pagination={false}
        locale={{ emptyText: <Empty description="暂无在线节点（Worker 进程心跳 10s 上报一次）" /> }}
      />
    </Card>
  )
}

export default Nodes
