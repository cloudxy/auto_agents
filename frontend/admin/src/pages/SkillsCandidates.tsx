/**
 * 候选审核 Tab（方案 A · A-P5-2）：市场采集候选 → 人工闸门 → 转正(import-url 管线)/拒绝。
 */
import React, { useCallback, useEffect, useState } from 'react'
import { Alert, Button, Empty, message, Popconfirm, Space, Table, Tag, Typography } from 'antd'

import {
  approveSkillCandidate, listSkillCandidates, rejectSkillCandidate,
  type SkillCandidate,
} from '../services/skills'
import { apiErrorMessage } from '../utils/errorMessage'

const { Text } = Typography

const SkillsCandidates: React.FC<{ canAdmin?: boolean }> = ({ canAdmin = false }) => {
  const [items, setItems] = useState<SkillCandidate[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [acting, setActing] = useState<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await listSkillCandidates()
      setItems(data.items)
      setTotal(data.total)
    } catch (e) {
      message.error(apiErrorMessage(e, '候选加载失败'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const approve = async (id: number) => {
    try {
      setActing(id)
      const result = await approveSkillCandidate(id)
      message.success(`已转正：${result.name ?? ''}（进入评分队列）`)
      load()
    } catch (e) {
      message.error(apiErrorMessage(e, '转正失败'))
    } finally {
      setActing(null)
    }
  }

  const reject = async (id: number) => {
    try {
      setActing(id)
      const result = await rejectSkillCandidate(id)
      message.success(result.blacklisted ? `已拒绝（同名技能 ${result.blacklisted} 已置 blacklist）` : '已拒绝')
      load()
    } catch (e) {
      message.error(apiErrorMessage(e, '拒绝失败'))
    } finally {
      setActing(null)
    }
  }

  return (
    <div>
      {!canAdmin && <Alert type="info" showIcon style={{ marginBottom: 12 }} message="转正/拒绝需 admin 权限" />}
      <Space style={{ marginBottom: 12 }}>
        <Button onClick={load}>刷新候选</Button>
        <Text type="secondary">共 {total} 条待审（来源：skill_harvester 采集，source=marketplace）</Text>
      </Space>
      <Table
        rowKey="id" size="small" loading={loading}
        locale={{ emptyText: <Empty description="暂无待审候选——运行 skill_harvester 任务后出现" /> }}
        pagination={{ pageSize: 10 }}
        dataSource={items}
        columns={[
          { title: '名称', dataIndex: 'title', render: (v: string) => <Text strong>{v}</Text> },
          { title: '来源', dataIndex: 'url', ellipsis: true, render: (v: string) => <a href={v} target="_blank" rel="noreferrer">{v}</a> },
          { title: '类型', dataIndex: 'kind', width: 120, render: (v: string) => <Tag>{v || '-'}</Tag> },
          { title: '描述', dataIndex: 'description', ellipsis: true },
          ...(canAdmin ? [{
            title: '操作', width: 160,
            render: (_: unknown, r: SkillCandidate) => (
              <Space size={0}>
                <Button type="link" size="small" loading={acting === r.id} onClick={() => approve(r.id)}>转正</Button>
                <Popconfirm title="确认拒绝该候选？" okText="拒绝" okButtonProps={{ danger: true }} cancelText="取消"
                            onConfirm={() => reject(r.id)}>
                  <Button type="link" danger size="small">拒绝</Button>
                </Popconfirm>
              </Space>
            ),
          }] : []),
        ]}
      />
    </div>
  )
}

export default SkillsCandidates
