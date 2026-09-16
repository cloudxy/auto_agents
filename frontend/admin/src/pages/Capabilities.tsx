/**
 * 能力市场：租户货架（屏 15）vs 超管七叶+总开关（屏 24）。
 * 租户无源/上架/扫描/总开关。无 enable-host。禁定价可买四字。
 */
import React, { useEffect, useState } from 'react'
import { Button, ConfigProvider, Tabs } from 'antd'
import { EyeOutlined, ImportOutlined } from '@ant-design/icons'
import { useNavigate, useSearchParams } from 'react-router-dom'

import Skills from './Skills'
import SubscribeModal from '../components/SubscribeModal'
import CatalogTab from './market/CatalogTab'
import ImportWizard from './market/ImportWizard'
import PluginTab from './market/PluginTab'
import PowerMarketSwitch from './market/PowerMarketSwitch'
import SourceTab from './market/SourceTab'
import TeamLeafTab from './market/TeamLeafTab'
import TenantShelf from './market/TenantShelf'
import TypeLeafTab from './market/TypeLeafTab'
import { usePermission } from '../hooks/usePermission'
import { IMPORT_ENTRY } from './market/importWizardCopy'
import {
  AGENT_EMPTY, COMMAND_EMPTY, TABS,
} from './market/marketCopy'
import './market/marketTabs.css'

const COMMAND_TYPES = ['command']
const AGENT_TYPES = ['agent', 'expert']

const Capabilities: React.FC = () => {
  const { isPlatformAdmin, role } = usePermission()
  const navigate = useNavigate()
  const [tab, setTab] = useState('catalog')
  const [params] = useSearchParams()
  const bounceType = params.get('subscribeType') || ''
  const bounceName = params.get('subscribeName') || ''
  const [target, setTarget] = useState<{ type: string; name: string } | null>(
    bounceType && bounceName ? { type: bounceType, name: bounceName } : null,
  )
  const [catalogFocus, setCatalogFocus] = useState<string | null>(null)
  const [importOpen, setImportOpen] = useState(false)
  const [catalogRefresh, setCatalogRefresh] = useState(0)
  /** T-13（FR-03 验收路径）：超管货架预览——与租户货架同一数据与口径，闸关下走此通道验收 */
  const [shelfPreview, setShelfPreview] = useState(false)

  useEffect(() => {
    if (bounceType && bounceName) setTarget({ type: bounceType, name: bounceName })
  }, [bounceType, bounceName])

  const openCatalog = (name: string) => {
    setCatalogFocus(name)
    setTab('catalog')
  }

  const closeImport = (imported: boolean) => {
    setImportOpen(false)
    if (imported) setCatalogRefresh((k) => k + 1)
  }
  const finishImport = () => {
    setCatalogRefresh((k) => k + 1)
    setTab('catalog')
    setImportOpen(false)
  }

  const modal = target ? (
    <SubscribeModal
      open
      assetType={target.type}
      assetName={target.name}
      onClose={() => setTarget(null)}
      onSubscribed={() => {
        setTarget(null)
        navigate('/capabilities/installs')
      }}
    />
  ) : null

  if (!isPlatformAdmin) {
    return (
      <ConfigProvider button={{ autoInsertSpace: false }}>
        <TenantShelf
          canSubscribe={role !== 'viewer'}
          onSubscribe={(type, name) => setTarget({ type, name })}
        />
        {modal}
      </ConfigProvider>
    )
  }

  return (
    <ConfigProvider button={{ autoInsertSpace: false }}>
    <div data-testid="governance-shell">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, gap: 12, flexWrap: 'wrap' }}>
        <PowerMarketSwitch />
        <div style={{ display: 'flex', gap: 8 }}>
          <Button
            icon={<EyeOutlined />}
            type={shelfPreview ? 'primary' : 'default'}
            aria-pressed={shelfPreview}
            onClick={() => setShelfPreview((v) => !v)}
          >
            货架预览
          </Button>
          <Button icon={<ImportOutlined />} onClick={() => setImportOpen(true)}>
            {IMPORT_ENTRY}
          </Button>
        </div>
      </div>
      {shelfPreview ? (
        <TenantShelf
          canSubscribe={role !== 'viewer'}
          onSubscribe={(type, name) => setTarget({ type, name })}
          onExitPreview={() => setShelfPreview(false)}
        />
      ) : (
      <Tabs
        className="market-tabs"
        activeKey={tab}
        onChange={setTab}
        more={{ icon: null }}
        animated={false}
        destroyOnHidden={false}
        items={[
          { key: TABS[0].key, label: TABS[0].label, children: <SourceTab /> },
          { key: TABS[1].key, label: TABS[1].label, children: (
            <CatalogTab focusName={catalogFocus} refreshKey={catalogRefresh} />
          ) },
          { key: TABS[2].key, label: TABS[2].label, children: (
            <PluginTab
              onSubscribe={(name) => setTarget({ type: 'plugin', name })}
              onOpenCatalog={openCatalog}
            />
          ) },
          { key: TABS[3].key, label: TABS[3].label, children: (
            <Skills onSubscribe={(name) => setTarget({ type: 'skill', name })} />
          ) },
          { key: TABS[4].key, label: TABS[4].label, children: (
            <TypeLeafTab types={COMMAND_TYPES} leaf="命令" emptyCopy={COMMAND_EMPTY}
                         onGoSource={() => setTab('sources')}
                         onSubscribe={(name) => setTarget({ type: 'command', name })} />
          ) },
          { key: TABS[5].key, label: TABS[5].label, children: (
            <TypeLeafTab types={AGENT_TYPES} leaf="智能体" emptyCopy={AGENT_EMPTY} />
          ) },
          { key: TABS[6].key, label: TABS[6].label, children: (
            <TeamLeafTab onSubscribe={(name) => setTarget({ type: 'team', name })} />
          ) },
        ]}
      />
      )}
      {importOpen ? (
        <ImportWizard open onCancel={closeImport} onFinished={finishImport} />
      ) : null}
      {modal}
    </div>
    </ConfigProvider>
  )
}

export default Capabilities
