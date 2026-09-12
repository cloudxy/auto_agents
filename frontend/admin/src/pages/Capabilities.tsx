/**
 * T-28 治理台七叶：源 | 目录 | 插件 | 技能 | 命令 | 智能体 | 专家团
 * 窄屏滚动不删叶。无「上架全部子资产」。无 enable-host。
 * T-36 页头动作行「导入资产」仅平台超管（GWT-100.6 无入口面）。
 */
import React, { useEffect, useState } from 'react'
import { Button, ConfigProvider, Tabs } from 'antd'
import { ImportOutlined } from '@ant-design/icons'
import { useSearchParams } from 'react-router-dom'

import Skills from './Skills'
import SubscribeModal from '../components/SubscribeModal'
import CatalogTab from './market/CatalogTab'
import ImportWizard from './market/ImportWizard'
import PluginTab from './market/PluginTab'
import SourceTab from './market/SourceTab'
import TeamLeafTab from './market/TeamLeafTab'
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
  const { isPlatformAdmin } = usePermission()
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

  useEffect(() => {
    if (bounceType && bounceName) setTarget({ type: bounceType, name: bounceName })
  }, [bounceType, bounceName])

  const openCatalog = (name: string) => {
    setCatalogFocus(name)
    setTab('catalog')
  }

  // T-36：导入成功后刷新目录；完成额外切到目录 tab（产物未上架，不跳公开商店）
  const closeImport = (imported: boolean) => {
    setImportOpen(false)
    if (imported) setCatalogRefresh((k) => k + 1)
  }
  const finishImport = () => {
    setCatalogRefresh((k) => k + 1)
    setTab('catalog')
    setImportOpen(false)
  }

  return (
    <ConfigProvider button={{ autoInsertSpace: false }}>
    <div>
      {isPlatformAdmin ? (
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
          <Button icon={<ImportOutlined />} onClick={() => setImportOpen(true)}>
            {IMPORT_ENTRY}
          </Button>
        </div>
      ) : null}
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
      {importOpen ? (
        <ImportWizard open onCancel={closeImport} onFinished={finishImport} />
      ) : null}
      {target ? (
        <SubscribeModal
          open
          assetType={target.type}
          assetName={target.name}
          onClose={() => setTarget(null)}
        />
      ) : null}
    </div>
    </ConfigProvider>
  )
}

export default Capabilities
