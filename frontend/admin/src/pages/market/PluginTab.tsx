import React, { useCallback, useEffect, useState } from 'react'
import {
  Alert, Button, Drawer, Empty, Space, Table, Tag, Typography, message,
} from 'antd'
import { ReloadOutlined, SafetyCertificateOutlined } from '@ant-design/icons'

import {
  getPlugin, listAssets, patchListing, scanPlugins, verifyPlugin,
  type AssetRow, type PluginDetail,
} from '../../services/capabilities'
import { usePermission } from '../../hooks/usePermission'
import { apiErrorMessage } from '../../utils/errorMessage'
import HostRuntimeNote from './HostRuntimeNote'
import ListingControls from './ListingControls'
import {
  DETAIL, HEALTH_UNKNOWN, LIST_CHILD, LISTED_NE_VERIFY,
  NEED_PLATFORM_ADMIN, OPEN_IN_CATALOG, VERIFY, healthLabel, loadFail,
} from './marketCopy'

const { Text } = Typography

type Props = { onSubscribe: (name: string) => void; onOpenCatalog: (name: string) => void }

const PluginTab: React.FC<Props> = ({ onSubscribe, onOpenCatalog }) => {
  const { isPlatformAdmin } = usePermission()
  const [rows, setRows] = useState<AssetRow[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [verifying, setVerifying] = useState<string | null>(null)
  const [detail, setDetail] = useState<PluginDetail | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try { setRows((await listAssets('plugin')).items) } catch (e) {
      setRows([])
      setError(apiErrorMessage(e, loadFail('插件')))
    } finally { setLoading(false) }
  }, [])
  useEffect(() => { load() }, [load])

  const scan = async () => {
    try {
      await scanPlugins()
      message.success('插件扫描完成')
      load()
    } catch (e) { message.error(apiErrorMessage(e, '扫描失败')) }
  }

  const verify = async (name: string) => {
    try {
      setVerifying(name)
      const result = await verifyPlugin(name)
      message.info(`验证 ${name}: ${healthLabel(result.health, Boolean(result.detail && Object.keys(result.detail).length))}`)
      load()
    } catch (e) {
      message.error(apiErrorMessage(e, '验证失败'))
    } finally { setVerifying(null) }
  }

  const openDetail = async (name: string) => {
    try { setDetail(await getPlugin(name)) } catch (e) {
      message.error(apiErrorMessage(e, '详情加载失败'))
    }
  }

  const replace = (next: AssetRow) => {
    setRows((cur) => cur.map((r) => (r.id === next.id ? { ...r, ...next } : r)))
    setNotice(null)
  }

  const empty = !loading && !error && rows.length === 0
  const bundled = (detail?.bundled_skills || []) as string[]

  return (
    <div>
      {notice ? <Alert type="error" showIcon title={notice} style={{ marginBottom: 12 }} /> : null}
      {error ? (
        <Alert type="error" showIcon title={error} action={<Button onClick={load}>重试</Button>} />
      ) : null}
      <Space style={{ marginBottom: 12 }} wrap>
        {isPlatformAdmin && <Button type="primary" onClick={scan}>扫描插件目录</Button>}
        <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
        <Text type="secondary">{LISTED_NE_VERIFY}</Text>
      </Space>
      {empty ? <Empty description="还没有插件。扫描或同步源后会出现在这里。" /> : (
        <Table rowKey="id" size="middle" loading={loading} dataSource={rows} pagination={false}
               columns={[
                 { title: '名称', dataIndex: 'name', render: (v: string) => <Text code>{v}</Text> },
                 { title: '描述', dataIndex: 'title', ellipsis: true },
                 { title: '上架', render: (_: unknown, r: AssetRow) => (
                   <ListingControls row={r} isPlatformAdmin={isPlatformAdmin}
                                    onChanged={replace} onError={setNotice} />
                 )},
                 { title: '操作', render: (_: unknown, r: AssetRow) => (
                   <Space>
                     <Button size="small" onClick={() => onSubscribe(r.name)}>订阅</Button>
                     <Button size="small" onClick={() => openDetail(r.name)}>{DETAIL}</Button>
                     <Button size="small" icon={<SafetyCertificateOutlined />}
                             loading={verifying === r.name}
                             disabled={!isPlatformAdmin}
                             onClick={() => verify(r.name)}>
                       {isPlatformAdmin ? VERIFY : NEED_PLATFORM_ADMIN}
                     </Button>
                   </Space>
                 )},
               ]} />
      )}
      <Drawer title={detail?.name || DETAIL} size="large" open={Boolean(detail)}
              onClose={() => setDetail(null)}>
        {detail ? (
          <Space orientation="vertical" style={{ width: '100%' }} size="middle">
            <Text>验证态 <Tag>{healthLabel(detail.health_status, Boolean(detail.mcp_servers && Object.keys(detail.mcp_servers).length))}</Tag></Text>
            {detail.health_status === 'unknown' ? <Text type="secondary">{HEALTH_UNKNOWN}</Text> : null}
            <HostRuntimeNote />
            {bundled.map((name) => (
              <Space key={name}>
                <Text code>{name}</Text>
                <Button size="small" onClick={() => onOpenCatalog(name)}>{OPEN_IN_CATALOG}</Button>
                <Button size="small" disabled={!isPlatformAdmin}
                        onClick={() => listChild(name, isPlatformAdmin, setNotice)}>{LIST_CHILD}</Button>
              </Space>
            ))}
          </Space>
        ) : null}
      </Drawer>
    </div>
  )
}

async function listChild(
  name: string, allowed: boolean, onError: (msg: string) => void,
) {
  if (!allowed) return
  try {
    await patchListing('skill', name, 'listed')
    message.success(`已单独上架 ${name}`)
  } catch (e) {
    onError(apiErrorMessage(e, '上架失败'))
  }
}

export default PluginTab
