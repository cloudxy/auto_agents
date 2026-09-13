/**
 * T-26 我的安装：五类分组；unlist 残留可卸；安装行只读 ≠ 只读角色。无 enable-host。
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Alert, Button, ConfigProvider, Empty, Modal, Switch, Table, Tag, Typography } from 'antd'

import SubscribeModal from '../components/SubscribeModal'
import TenantSpaceOnly from '../components/TenantSpaceOnly'
import { useAuthStore } from '../store/useAuthStore'
import {
  listInstalls, patchInstall, uninstallInstall, type InstallRow,
} from '../services/capabilities'
import {
  DELISTED, DELISTED_RESUBSCRIBE, EMPTY_COPY, EMPTY_CTA,
  GROUP_LABELS, GROUP_ORDER, HOST_LABELS, READONLY_UNINSTALL_TIP, TRUST_CONFIRM,
  loadErrorCopy, publicType, uninstallConfirm, uninstallErrorCopy,
} from './installsCopy'

const { Text } = Typography
const OFFICIAL_MARKET = `${(process.env.REACT_APP_OFFICIAL_URL || 'http://localhost:9113').replace(/\/$/, '')}/capabilities`

const groupRows = (items: InstallRow[]) => {
  const buckets: Record<string, InstallRow[]> = {}
  for (const row of items) {
    const key = publicType(row.asset_type)
    buckets[key] = buckets[key] || []
    buckets[key].push(row)
  }
  return GROUP_ORDER.filter((type) => (buckets[type] || []).length > 0).map((type) => ({
    type, label: GROUP_LABELS[type], rows: buckets[type],
  }))
}

const MyInstalls: React.FC = () => {
  const user = useAuthStore((s) => s.user)
  // GWT-82.4：平台超管无企业空间 → 「属于企业空间」说明态，不发空表请求
  const noTenantSpace = Boolean(user?.is_platform_admin) && user?.tenant_id == null
  const [items, setItems] = useState<InstallRow[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [pending, setPending] = useState<InstallRow | null>(null)
  const [uninstallErr, setUninstallErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [trustRow, setTrustRow] = useState<InstallRow | null>(null)
  const [subscribe, setSubscribe] = useState<InstallRow | null>(null)

  const load = useCallback(async () => {
    if (noTenantSpace) return
    setLoadError(null)
    try {
      setItems((await listInstalls()).items)
    } catch (e) {
      setItems(null)
      setLoadError(loadErrorCopy(e))
    }
  }, [noTenantSpace])

  useEffect(() => { load() }, [load])

  const replaceRow = (next: InstallRow) => {
    setItems((cur) => (cur || []).map((row) => (row.id === next.id ? { ...row, ...next } : row)))
  }

  const onEnabled = async (row: InstallRow, on: boolean) => {
    if (!row.can_change_flags) return
    replaceRow(await patchInstall(row.id, { enabled: on ? 1 : 0 }))
  }

  const onTrustSwitch = (row: InstallRow, on: boolean) => {
    if (!row.can_change_flags) return
    if (on) { setTrustRow(row); return }
    patchInstall(row.id, { trusted: 0 }).then(replaceRow)
  }

  const confirmTrust = async () => {
    if (!trustRow) return
    replaceRow(await patchInstall(trustRow.id, { trusted: 1 }))
    setTrustRow(null)
  }

  const confirmUninstall = async () => {
    if (!pending) return
    setBusy(true)
    setUninstallErr(null)
    try {
      await uninstallInstall(pending.id)
      setItems((cur) => (cur || []).filter((row) => row.id !== pending.id))
      setPending(null)
    } catch (e) {
      setUninstallErr(uninstallErrorCopy(e))
    } finally {
      setBusy(false)
    }
  }

  const groups = useMemo(() => groupRows(items || []), [items])
  const empty = !loadError && items !== null && items.length === 0

  if (noTenantSpace) return <TenantSpaceOnly what="安装" />

  return (
    <ConfigProvider button={{ autoInsertSpace: false }}>
    <div>
      {loadError ? (
        <Alert type="error" showIcon title={loadError} action={<Button onClick={load}>重试</Button>} />
      ) : null}
      {empty ? (
        <Empty description={EMPTY_COPY}>
          <Button type="primary" href={OFFICIAL_MARKET}>{EMPTY_CTA}</Button>
        </Empty>
      ) : null}
      {items === null && !loadError ? <Text type="secondary">加载中…</Text> : null}
      {groups.map((g) => (
        <div key={g.type} style={{ marginBottom: 24 }}>
          <Typography.Title level={5}>{g.label}</Typography.Title>
          <InstallTable
            rows={g.rows}
            onEnabled={onEnabled}
            onTrust={onTrustSwitch}
            onUninstall={(row) => { setUninstallErr(null); setPending(row) }}
            onResubscribe={setSubscribe}
          />
        </div>
      ))}
      {pending ? (
        <Modal
          open
          title={uninstallConfirm(pending)}
          okText="卸载"
          okButtonProps={{ danger: true, loading: busy }}
          cancelText="取消"
          onOk={confirmUninstall}
          onCancel={() => { if (!busy) setPending(null) }}
          destroyOnHidden
        >
          {uninstallErr ? <Alert type="error" showIcon title={uninstallErr} /> : null}
        </Modal>
      ) : null}
      {trustRow ? (
        <Modal
          open
          title={TRUST_CONFIRM}
          okText="打开信任"
          onOk={confirmTrust}
          onCancel={() => setTrustRow(null)}
          destroyOnHidden
        />
      ) : null}
      {subscribe ? (
        <SubscribeModal
          open
          assetType={subscribe.asset_type}
          assetName={subscribe.asset_name}
          onClose={() => setSubscribe(null)}
          onSubscribed={() => { setSubscribe(null); load() }}
        />
      ) : null}
    </div>
    </ConfigProvider>
  )
}

interface TableProps {
  rows: InstallRow[]
  onEnabled: (row: InstallRow, on: boolean) => void
  onTrust: (row: InstallRow, on: boolean) => void
  onUninstall: (row: InstallRow) => void
  onResubscribe: (row: InstallRow) => void
}

const InstallTable: React.FC<TableProps> = ({
  rows, onEnabled, onTrust, onUninstall, onResubscribe,
}) => (
  <Table
    rowKey="id"
    size="small"
    pagination={false}
    dataSource={rows}
    columns={[
      { title: '名称', dataIndex: 'asset_name' },
      { title: '宿主', dataIndex: 'host', render: (host: string) => HOST_LABELS[host] || host },
      {
        title: '上架残留',
        render: (_: unknown, row: InstallRow) => (
          row.delisted ? <Tag color="default">{row.delisted_label || DELISTED}</Tag> : null
        ),
      },
      {
        title: '启用',
        render: (_: unknown, row: InstallRow) => (
          <Switch
            checked={row.enabled === 1}
            disabled={!row.can_change_flags}
            onChange={(on) => onEnabled(row, on)}
          />
        ),
      },
      {
        title: '信任',
        render: (_: unknown, row: InstallRow) => (
          <Switch
            checked={row.trusted === 1}
            disabled={!row.can_change_flags}
            onChange={(on) => onTrust(row, on)}
          />
        ),
      },
      {
        title: '卸载',
        render: (_: unknown, row: InstallRow) => (
          <Button
            danger
            disabled={!row.can_uninstall}
            title={row.can_uninstall ? undefined : READONLY_UNINSTALL_TIP}
            onClick={() => onUninstall(row)}
          >
            卸载
          </Button>
        ),
      },
      {
        title: '再订',
        render: (_: unknown, row: InstallRow) => {
          const hint = row.resubscribe_hint || (row.delisted ? DELISTED_RESUBSCRIBE : '')
          const disabled = row.resubscribe_allowed === false
          return (
            <div>
              <Button disabled={disabled} onClick={() => onResubscribe(row)}>再订</Button>
              {disabled && hint ? <div><Text type="secondary">{hint}</Text></div> : null}
            </div>
          )
        },
      },
    ]}
  />
)

export default MyInstalls
