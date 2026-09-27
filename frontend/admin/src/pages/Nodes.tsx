/**
 * Worker 节点页面（阶段 2.2）
 *
 * 数据源：/spiders/nodes（Redis 心跳键扫描）
 * 展示：在线状态、进程信息、承载爬虫、各爬虫当前活跃任务
 */
import React from 'react'
import { Card, Table, Tag, Button, Space, Badge, Typography } from 'antd'
import { ClusterOutlined, ReloadOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { fetchNodesPage } from '../services/admin'
import { LoadEmpty, LoadFailure } from '../components/LoadState'

const { Text } = Typography

// T-17 / FR-84：失败≠空——失败句 + 重试；真 0（接口成功且 0 节点）才走「还没有…」
const NODES_LOAD_FAILED = '节点状态加载失败。检查网络后重试。'
const EMPTY_NODES = '还没有在线采集节点。没有在线工人时提交会被拦住，不会出数。'

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
  // 工单 78：react-query 托管（心跳 10s 续约，15s 轮询跟上离线判定；失焦自动暂停）
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['spider-nodes'],
    queryFn: () => fetchNodesPage<WorkerNode>(),
    refetchInterval: 15000,
  })
  const nodes = data?.items || []
  const total = data?.total || 0

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
        <Space orientation="vertical" size={0}>
          <Text strong><ClusterOutlined style={{ marginRight: 6 }} />{record.worker_id}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            PID {record.pid ?? '-'} · 启动于 {record.started_at || '-'} · 重启 {record.respawn_count} 次
          </Text>
        </Space>
      ),
    },
    {
      title: '承载采集方案',
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
      title={<span><ClusterOutlined style={{ marginRight: 8 }} />Worker 节点{data ? `（共 ${total} 个）` : ''}</span>}
      extra={<Button icon={<ReloadOutlined />} onClick={() => refetch()}>刷新</Button>}
    >
      {/* GWT-84.1：失败=失败句+可点重试，不画成「暂无在线节点」空表；标题数只在有数据时出现 */}
      {isError ? (
        <LoadFailure title={NODES_LOAD_FAILED} onRetry={() => refetch()} />
      ) : nodes.length === 0 && !isLoading ? (
        <LoadEmpty title={EMPTY_NODES} />
      ) : (
        <Table
          columns={columns}
          dataSource={nodes}
          rowKey="worker_id"
          loading={isLoading}
          pagination={false}
        />
      )}
    </Card>
  )
}

export default Nodes
