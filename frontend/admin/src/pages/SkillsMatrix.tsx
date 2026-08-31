/**
 * 适配器矩阵 Tab（方案 A · A-P3-2）：行=skill、列=tool 的勾选矩阵 + 触发 sync。
 * 数据源：技能名来自技能库列表；工具列来自 manifests 文件名。
 */
import React, { useCallback, useEffect, useState } from 'react'
import { Alert, Button, Checkbox, message, Space, Spin, Table, Tag, Typography } from 'antd'
import { SyncOutlined } from '@ant-design/icons'

import { listManifests, syncAdapters, updateManifest } from '../services/skills'

const { Text } = Typography

const SkillsMatrix: React.FC<{ skillNames: string[]; canAdmin?: boolean }> = ({ skillNames, canAdmin = false }) => {
  const [manifests, setManifests] = useState<Record<string, string[]>>({})
  const [loading, setLoading] = useState(false)
  const [savingTool, setSavingTool] = useState<string | null>(null)
  const [syncOutput, setSyncOutput] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setManifests(await listManifests())
    } catch (e) {
      message.error(`矩阵加载失败: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const toggle = async (tool: string, name: string, checked: boolean) => {
    const current = manifests[tool] ?? []
    const next = checked ? [...current, name] : current.filter((n) => n !== name)
    setSavingTool(tool)
    try {
      await updateManifest(tool, next)
      setManifests((m) => ({ ...m, [tool]: next }))
    } catch (e) {
      message.error(`保存失败: ${e instanceof Error ? e.message : String(e)}`)
      load()
    } finally {
      setSavingTool(null)
    }
  }

  const runSync = async () => {
    try {
      const result = await syncAdapters()
      setSyncOutput(result.output || `returncode=${result.returncode}`)
      result.ok ? message.success('适配器同步完成') : message.error('适配器同步失败，见输出')
    } catch (e) {
      message.error(`同步失败: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const tools = Object.keys(manifests)

  return (
    <div>
      {!canAdmin && <Alert type="info" showIcon style={{ marginBottom: 12 }} message="矩阵编辑与同步需 admin 权限" />}
      <Space style={{ marginBottom: 12 }}>
        <Button onClick={load}>刷新矩阵</Button>
        {canAdmin && <Button type="primary" icon={<SyncOutlined />} onClick={runSync}>触发 sync.sh 分发</Button>}
      </Space>
      {loading ? <Spin /> : tools.length === 0 ? (
        <Text type="secondary">manifests 目录为空——在 skills-library/manifests/ 添加 <Text code>{'<tool>.yaml'}</Text> 后刷新</Text>
      ) : (
        <Table
          rowKey="name" size="small" pagination={false}
          dataSource={skillNames.map((name) => ({ name }))}
          columns={[
            { title: '技能', dataIndex: 'name', render: (n: string) => <Text code>{n}</Text> },
            ...tools.map((tool) => ({
              title: <span>{tool} <Tag style={{ marginLeft: 4 }}>{(manifests[tool] ?? []).length}</Tag></span>,
              render: (_: unknown, row: { name: string }) => (
                <Checkbox
                  disabled={!canAdmin || savingTool === tool}
                  checked={(manifests[tool] ?? []).includes(row.name)}
                  onChange={(e) => toggle(tool, row.name, e.target.checked)}
                />
              ),
            })),
          ]}
        />
      )}
      {syncOutput && (
        <Alert type="success" style={{ marginTop: 12, whiteSpace: 'pre-wrap', fontFamily: 'monospace' }} message={syncOutput} />
      )}
    </div>
  )
}

export default SkillsMatrix
