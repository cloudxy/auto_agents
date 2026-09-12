/**
 * 值班页 /newapi：T-18 数据面 + T-31 页头结构 + T-32/33 总览三问驾驶舱。
 * T-31（GWT-98.1 = FR-99 §0.10）：总览/探针/事件三 tab 上提顶栏行（PageHeaderTabs
 * 槽位），页内无标题卡；内容区直接以当前 tab 内容开始（pane 常挂载保住筛选分页态）。
 * T-32/33：总览 tab = 三问驾驶舱（Overview3q：三区独立失败/置顶排序/立即探测/事件跳转），
 * 数据面 react-query 化；探针/事件 pane 与窗口配置 Modal 保持不动（GWT-99.3 动作不回退）。
 */
import React, { useCallback, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import ProbeResults from '../components/newapi/ProbeResults'
import EventsList from '../components/newapi/EventsList'
import Overview3q from '../components/newapi/Overview3q'
import PageHeaderTabs, { pageTabPaneStyle } from '../components/layout/PageHeaderTabs'
import { Button, Form, InputNumber, Modal, Popconfirm, message } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { clearModelConfig, setModelConfig } from '../services/newapi'
import type { GatewayModelWithConfig } from '../services/newapi'

/** 页级 tab（§0.10：顶栏行 = 页名「中转站管控」+ 本三 tab，与欢迎语同一行） */
const PAGE_TAB_ITEMS = [
  { key: 'overview', label: '总览' },
  { key: 'probes', label: '探针' },
  { key: 'events', label: '事件' },
]

const NewApiOps: React.FC = () => {
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState('overview')
  // pane 与原 Tabs 同语义：首次激活才挂载（数据装配时机不变），此后保持挂载（筛选/分页态不丢）
  const [visitedTabs, setVisitedTabs] = useState<Record<string, boolean>>({ overview: true })
  // GWT-98.5：总览 Top N 跳入事件 tab 的目标行（高亮）
  const [highlightEventId, setHighlightEventId] = useState<number | undefined>(undefined)
  const onTabChange = useCallback((key: string) => {
    setActiveTab(key)
    setVisitedTabs((visited) => (visited[key] ? visited : { ...visited, [key]: true }))
  }, [])

  const onJumpToEvent = useCallback((eventId: number) => {
    setHighlightEventId(eventId)
    onTabChange('events')
  }, [onTabChange])

  const [cfgTarget, setCfgTarget] = useState<GatewayModelWithConfig | null>(null)
  const [cfgSaving, setCfgSaving] = useState(false)
  const [cfgForm] = Form.useForm()
  const [refreshSignal, setRefreshSignal] = useState(0)
  const [configSaved, setConfigSaved] = useState(0)

  const openCfg = (record: GatewayModelWithConfig) => {
    setCfgTarget(record)
    cfgForm.setFieldsValue({
      limit_quota: record.effective.limit_quota,
      window_hours: record.effective.window_hours,
      cooldown_seconds: record.effective.cooldown_seconds,
    })
  }

  const onSaveCfg = async () => {
    if (!cfgTarget) return
    try {
      const values = await cfgForm.validateFields()
      setCfgSaving(true)
      await setModelConfig(cfgTarget.gateway_ref, values)
      message.success(`模型 ${cfgTarget.model_name} 窗口配置已保存`)
      setCfgTarget(null)
      queryClient.invalidateQueries({ queryKey: ['newapi'] })
      setConfigSaved((s) => s + 1)
    } catch (error) {
      if ((error as { errorFields?: unknown })?.errorFields) return
      message.error('保存窗口配置失败')
    } finally {
      setCfgSaving(false)
    }
  }

  const onClearCfg = async () => {
    if (!cfgTarget) return
    try {
      setCfgSaving(true)
      await clearModelConfig(cfgTarget.gateway_ref)
      message.success(`模型 ${cfgTarget.model_name} 已清除窗口配置`)
      setCfgTarget(null)
      queryClient.invalidateQueries({ queryKey: ['newapi'] })
      setConfigSaved((s) => s + 1)
    } catch (error) {
      message.error('清除窗口配置失败')
    } finally {
      setCfgSaving(false)
    }
  }

  // 顶栏「刷新」动作等价保持（GWT-99.3）：驾驶舱走 react-query 失效，探针/事件 pane 走信号
  const refreshAll = () => {
    queryClient.invalidateQueries({ queryKey: ['newapi'] })
    setRefreshSignal((s) => s + 1)
  }

  return (
    <>
      {/* 页级 tab 上提顶栏（GWT-98.1）；无槽位（单测直渲染）时本组件原位回退 */}
      <PageHeaderTabs items={PAGE_TAB_ITEMS} activeKey={activeTab} onChange={onTabChange} />

      {/* 动作行（原 Card extra 的「刷新」保持，GWT-99.3 动作等价；作用于全部 tab） */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
        <Button icon={<ReloadOutlined />} onClick={refreshAll}>
          刷新
        </Button>
      </div>

      {/* 内容区直接开始；pane 首次激活挂载后保持（与原 Tabs 同语义），display 切换 + ≤150ms 透明度过渡 */}
      {visitedTabs.overview && (
        <div style={pageTabPaneStyle(activeTab === 'overview')}>
          <Overview3q onOpenConfig={openCfg} onJumpToEvent={onJumpToEvent} />
        </div>
      )}
      {visitedTabs.probes && (
        <div style={pageTabPaneStyle(activeTab === 'probes')}>
          <ProbeResults refreshSignal={refreshSignal} />
        </div>
      )}
      {visitedTabs.events && (
        <div style={pageTabPaneStyle(activeTab === 'events')}>
          <EventsList
            refreshSignal={refreshSignal}
            configSaved={configSaved}
            highlightId={highlightEventId}
          />
        </div>
      )}

      <Modal
        title={`窗口配置 ${cfgTarget?.model_name ?? ''}`}
        open={!!cfgTarget}
        onOk={onSaveCfg}
        onCancel={() => setCfgTarget(null)}
        confirmLoading={cfgSaving}
        okText="保存"
        cancelText="取消"
        destroyOnHidden
      >
        <Form form={cfgForm} layout="vertical">
          <Form.Item name="limit_quota" label="窗口用量上限" rules={[{ required: true }]}>
            <InputNumber min={0} step={100} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="window_hours" label="统计窗口（小时）" initialValue={24} rules={[{ required: true }]}>
            <InputNumber min={1} max={720} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="cooldown_seconds" label="超限冷却（秒）" initialValue={3600} rules={[{ required: true }]}>
            <InputNumber min={60} max={604800} step={60} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
        {cfgTarget?.config && (
          <Popconfirm
            title="确认清除该模型的窗口配置？"
            okText="清除" okButtonProps={{ danger: true }} onConfirm={onClearCfg}
          >
            <Button danger type="link" style={{ padding: 0 }} disabled={cfgSaving}>
              清除窗口配置
            </Button>
          </Popconfirm>
        )}
      </Modal>
    </>
  )
}

export default NewApiOps
