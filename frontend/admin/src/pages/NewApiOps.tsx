/**
 * 值班页 /newapi（T-18）：网关模型/部署；空态 71.2 / 降级 71.3；URL 保留
 */
import React, { useCallback, useEffect, useState } from 'react'
import ProbeResults from '../components/newapi/ProbeResults'
import EventsList from '../components/newapi/EventsList'
import {
  DUTY_DEGRADE_71_3,
  DUTY_DEGRADE_71_3_HINT,
  DUTY_EMPTY_71_2,
  DUTY_EMPTY_71_2_HINT,
  DUTY_LOAD_FAILED,
  DUTY_TABLE_UNAVAILABLE,
  VERDICT_TAG,
  fmtQuota,
} from '../components/newapi/newapiShared'
import {
  Alert, Button, Card, Empty, Form, InputNumber, Modal, Popconfirm, Space, Statistic,
  Table, Tabs, Tag, Tooltip, Typography, message,
} from 'antd'
import { ReloadOutlined, SettingOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  clearModelConfig, fetchChannelsWithConfig, fetchNewapiOverview, setModelConfig,
} from '../services/newapi'
import type {
  GatewayModelWithConfig, NewapiOverview, ProbeVerdict,
} from '../services/newapi'

const { Text } = Typography

const NewApiOps: React.FC = () => {
  const [overview, setOverview] = useState<NewapiOverview | null>(null)
  const [overviewLoading, setOverviewLoading] = useState(false)
  const [loadFailed, setLoadFailed] = useState(false)

  const loadOverview = useCallback(async (showSpin = true) => {
    if (showSpin) setOverviewLoading(true)
    try {
      setOverview(await fetchNewapiOverview())
      setLoadFailed(false)
    } catch (error) {
      setLoadFailed(true)
      message.error(DUTY_LOAD_FAILED)
    } finally {
      if (showSpin) setOverviewLoading(false)
    }
  }, [])

  const [channelsCfg, setChannelsCfg] = useState<GatewayModelWithConfig[]>([])
  const [channelsCfgLoading, setChannelsCfgLoading] = useState(false)
  const [cfgTarget, setCfgTarget] = useState<GatewayModelWithConfig | null>(null)
  const [cfgSaving, setCfgSaving] = useState(false)
  const [cfgForm] = Form.useForm()
  const [refreshSignal, setRefreshSignal] = useState(0)
  const [configSaved, setConfigSaved] = useState(0)

  const loadChannelsCfg = useCallback(async (showSpin = true) => {
    if (showSpin) setChannelsCfgLoading(true)
    try {
      setChannelsCfg(await fetchChannelsWithConfig())
    } catch (error) {
      setChannelsCfg([])
    } finally {
      if (showSpin) setChannelsCfgLoading(false)
    }
  }, [])

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
      loadChannelsCfg(false)
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
      loadChannelsCfg(false)
      setConfigSaved((s) => s + 1)
    } catch (error) {
      message.error('清除窗口配置失败')
    } finally {
      setCfgSaving(false)
    }
  }

  useEffect(() => {
    loadOverview()
    loadChannelsCfg()
  }, [loadOverview, loadChannelsCfg])

  const refreshAll = () => {
    loadOverview(false)
    loadChannelsCfg(false)
    setRefreshSignal((s) => s + 1)
  }

  const channelColumns: ColumnsType<GatewayModelWithConfig> = [
    {
      title: '模型/部署', dataIndex: 'model_name', key: 'model_name', width: 200,
      render: (v: string) => <Text strong>{v || '-'}</Text>,
    },
    {
      title: '引用', dataIndex: 'gateway_ref', key: 'gateway_ref', width: 180, ellipsis: true,
      render: (v: string) => <Text code style={{ fontSize: 12 }}>{v}</Text>,
    },
    {
      title: '上游地址', dataIndex: 'api_base', key: 'api_base', ellipsis: true,
      render: (v: string | null | undefined) => v || '-',
    },
    {
      title: '密钥', dataIndex: 'api_key_masked', key: 'api_key_masked', width: 120,
      render: (v: string | null | undefined) => (v ? <Text code>{v}</Text> : '—'),
    },
    {
      title: '额度调度', key: 'quota_cfg', width: 190,
      render: (_: unknown, record: GatewayModelWithConfig) => {
        const sourceMeta: Record<string, { color: string; text: string }> = {
          channel: { color: 'blue', text: '模型级' },
          global: { color: 'cyan', text: '全局默认' },
          none: { color: 'default', text: '未纳管' },
        }
        const meta = sourceMeta[record.effective_source] || sourceMeta.none
        return (
          <Space size={4}>
            <Tooltip title={`窗口 ${record.effective.window_hours}h / 冷却 ${record.effective.cooldown_seconds}s`}>
              <Tag color={meta.color}>
                {record.effective_source === 'none' ? '未纳管' : fmtQuota(record.effective.limit_quota)}
              </Tag>
            </Tooltip>
            <Button type="link" size="small" icon={<SettingOutlined />} onClick={() => openCfg(record)}>
              配置
            </Button>
          </Space>
        )
      },
    },
  ]

  const verdicts = overview?.latest_batch_verdicts || {}
  const reachableEmpty = Boolean(overview?.available && (overview?.total ?? 0) === 0)
  const tableEmpty = overview && !overview.available
    ? DUTY_TABLE_UNAVAILABLE
    : reachableEmpty
      ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={
            <span>
              <div>{overview?.empty_state || DUTY_EMPTY_71_2}</div>
              <Text type="secondary">{DUTY_EMPTY_71_2_HINT}</Text>
            </span>
          }
        >
          <Button type="primary" onClick={refreshAll}>刷新</Button>
        </Empty>
      )
      : DUTY_EMPTY_71_2

  const renderOverviewTab = () => (
    <>
      {loadFailed && (
        <Alert
          type="error" showIcon style={{ marginBottom: 16 }}
          title={DUTY_LOAD_FAILED}
        />
      )}
      {overview && !overview.available && (
        <Alert
          type="warning" showIcon style={{ marginBottom: 16 }}
          title={overview.degrade_state || DUTY_DEGRADE_71_3}
          description={DUTY_DEGRADE_71_3_HINT}
        />
      )}
      <Space size={40} wrap style={{ marginBottom: 16 }}>
        <Statistic title="模型/部署" value={overview?.available ? overview.total : '-'} />
        <Statistic title="近 24h 事件数" value={overview?.events_24h ?? '-'} />
        <div>
          <div style={{ color: 'rgba(0,0,0,0.45)', fontSize: 14, marginBottom: 4 }}>
            最近探针批次{overview?.latest_batch_id ? `（${overview.latest_batch_id.slice(0, 8)}…）` : ''}
          </div>
          <Space size={8} wrap>
            {(['original', 'spoofed', 'offline'] as ProbeVerdict[]).map((v) => (
              <Tag key={v} color={VERDICT_TAG[v].color}>
                {VERDICT_TAG[v].text}: {verdicts[v] ?? 0}
              </Tag>
            ))}
          </Space>
        </div>
      </Space>
      <Table
        columns={channelColumns}
        dataSource={overview?.available ? channelsCfg : []}
        rowKey="gateway_ref"
        loading={overviewLoading || channelsCfgLoading}
        pagination={false}
        scroll={{ x: 900 }}
        locale={{ emptyText: tableEmpty }}
      />
    </>
  )

  return (
    <Card
      title="LLM 网关值班"
      extra={
        <Button icon={<ReloadOutlined />} onClick={refreshAll} loading={overviewLoading}>
          刷新
        </Button>
      }
    >
      <Tabs
        defaultActiveKey="overview"
        items={[
          { key: 'overview', label: '总览', children: renderOverviewTab() },
          { key: 'probes', label: '探针', children: <ProbeResults refreshSignal={refreshSignal} /> },
          { key: 'events', label: '事件', children: <EventsList refreshSignal={refreshSignal} configSaved={configSaved} /> },
        ]}
      />

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
    </Card>
  )
}

export default NewApiOps
