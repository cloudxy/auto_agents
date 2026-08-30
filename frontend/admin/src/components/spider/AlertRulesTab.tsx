/**
 * AlertRulesTab - 告警规则管理（列表 + 创建/编辑/启停/删除）
 */
import React, { useCallback, useEffect, useState } from 'react'
import {
  Table, Button, Tag, Space, Modal, Form, Select, Input, InputNumber, Switch,
  Popconfirm, Empty, Typography, message,
} from 'antd'
import { PlusOutlined, ReloadOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  fetchAlertRules, createAlertRule, updateAlertRule, deleteAlertRule,
} from '../../services/spiders'
import type { AlertRule, SpiderRegistry, SpiderMap } from './types'

const { Text } = Typography

const RULE_TYPE_LABELS: Record<string, string> = {
  consecutive_failures: '连续失败',
  result_drop: '结果下降',
  task_timeout: '任务超时',
  queue_depth: '队列堆积',
}

const SEVERITY_META: Record<string, { label: string; color: string }> = {
  info: { label: '信息', color: 'blue' },
  warning: { label: '警告', color: 'orange' },
  critical: { label: '严重', color: 'red' },
}

export interface AlertRulesTabProps {
  registry: SpiderRegistry
  spiderMap: SpiderMap
  isAdmin: boolean
}

export const AlertRulesTab: React.FC<AlertRulesTabProps> = ({
  registry, spiderMap, isAdmin,
}) => {
  const [alertRules, setAlertRules] = useState<AlertRule[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingRule, setEditingRule] = useState<AlertRule | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm()

  const loadAlertRules = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetchAlertRules()
      setAlertRules(res || [])
    } catch (error) {
      message.error('获取告警规则失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadAlertRules()
  }, [loadAlertRules])

  const openModal = (rule?: AlertRule) => {
    form.resetFields()
    if (rule) {
      setEditingRule(rule)
      form.setFieldsValue({
        name: rule.name,
        spider_name: rule.spider_name,
        rule_type: rule.rule_type,
        threshold: rule.threshold,
        window_minutes: rule.window_minutes,
        severity: rule.severity,
        enabled: rule.enabled,
      })
    } else {
      setEditingRule(null)
    }
    setModalOpen(true)
  }

  const onSubmit = async () => {
    try {
      const values = await form.validateFields()
      setSubmitting(true)
      if (editingRule) {
        await updateAlertRule(editingRule.id, values)
        message.success('告警规则已更新')
      } else {
        await createAlertRule(values)
        message.success('告警规则已创建')
      }
      setModalOpen(false)
      loadAlertRules()
    } catch (error: any) {
      if (error?.errorFields) return
      message.error(error?.response?.data?.message || error?.response?.data?.detail || '操作失败')
    } finally {
      setSubmitting(false)
    }
  }

  const onToggle = async (rule: AlertRule, enabled: boolean) => {
    try {
      await updateAlertRule(rule.id, { enabled })
      message.success(enabled ? '规则已启用' : '规则已停用')
      loadAlertRules()
    } catch (error: any) {
      message.error(error?.response?.data?.message || error?.response?.data?.detail || '操作失败')
    }
  }

  const onDelete = async (rule: AlertRule) => {
    try {
      await deleteAlertRule(rule.id)
      message.success(`告警规则"${rule.name}"已删除`)
      loadAlertRules()
    } catch (error: any) {
      message.error(error?.response?.data?.message || error?.response?.data?.detail || '删除失败')
    }
  }

  const columns: ColumnsType<AlertRule> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '规则名称', dataIndex: 'name', key: 'name' },
    {
      title: '爬虫', dataIndex: 'spider_name', key: 'spider_name',
      render: (name: string | null) => name ? (spiderMap[name]?.title || name) : <Tag>全局</Tag>,
    },
    {
      title: '类型', dataIndex: 'rule_type', key: 'rule_type', width: 120,
      render: (type: string) => <Tag color="purple">{RULE_TYPE_LABELS[type] || type}</Tag>,
    },
    {
      title: '阈值', dataIndex: 'threshold', key: 'threshold', width: 100,
      render: (v: number, record: AlertRule) => {
        if (record.rule_type === 'result_drop') return `${v}%`
        if (record.rule_type === 'task_timeout') return `${v}分钟`
        return v
      },
    },
    {
      title: '严重度', dataIndex: 'severity', key: 'severity', width: 90,
      render: (severity: string) => {
        const meta = SEVERITY_META[severity] || SEVERITY_META.warning
        return <Tag color={meta.color}>{meta.label}</Tag>
      },
    },
    { title: '窗口', dataIndex: 'window_minutes', key: 'window_minutes', width: 80,
      render: (v: number) => `${v}分钟` },
    { title: '上次触发', dataIndex: 'last_triggered_at', key: 'last_triggered_at', width: 170,
      render: (v: string | null) => v || '-' },
    {
      title: '启用', dataIndex: 'enabled', key: 'enabled', width: 80,
      render: (enabled: boolean, record: AlertRule) => (
        <Switch checked={enabled} size="small" disabled={!isAdmin} onChange={(v) => onToggle(record, v)} />
      ),
    },
    {
      title: '操作', key: 'action', width: 140,
      render: (_: any, record: AlertRule) => (
        <Space size="small">
          {isAdmin && (
            <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openModal(record)}>
              编辑
            </Button>
          )}
          {isAdmin && (
            <Popconfirm
              title="确认删除该告警规则？"
              okText="删除"
              okButtonProps={{ danger: true }}
              cancelText="取消"
              onConfirm={() => onDelete(record)}
            >
              <Button type="link" danger size="small" icon={<DeleteOutlined />}>删除</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  return (
    <>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          配置告警规则：连续失败、结果下降、任务超时等场景自动触发告警通知。
        </Text>
        <Space>
          {isAdmin && (
            <Button type="primary" icon={<PlusOutlined />} onClick={() => openModal()}>
              新建规则
            </Button>
          )}
          <Button icon={<ReloadOutlined />} onClick={loadAlertRules}>刷新</Button>
        </Space>
      </div>
      <Table
        columns={columns}
        dataSource={alertRules}
        rowKey="id"
        loading={loading}
        pagination={false}
        locale={{ emptyText: <Empty description="暂无告警规则" /> }}
      />

      <Modal
        title={editingRule ? '编辑告警规则' : '新建告警规则'}
        open={modalOpen}
        onOk={onSubmit}
        onCancel={() => setModalOpen(false)}
        confirmLoading={submitting}
        okText={editingRule ? '保存' : '创建'}
        destroyOnHidden
        width={520}
      >
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item
            name="name"
            label="规则名称"
            rules={[{ required: true, message: '请输入规则名称' }]}
          >
            <Input placeholder="如：百度热搜连续失败告警" />
          </Form.Item>

          <Form.Item
            name="spider_name"
            label="爬虫（留空为全局规则）"
          >
            <Select
              allowClear
              placeholder="选择爬虫（留空表示全局规则）"
              options={registry.spiders.map((s) => ({
                label: `${s.title}（${s.name}）`,
                value: s.name,
              }))}
            />
          </Form.Item>

          <Form.Item
            name="rule_type"
            label="规则类型"
            rules={[{ required: true, message: '请选择规则类型' }]}
          >
            <Select
              placeholder="选择规则类型"
              options={[
                { value: 'consecutive_failures', label: '连续失败（次数）' },
                { value: 'result_drop', label: '结果下降（百分比）' },
                { value: 'task_timeout', label: '任务超时（分钟）' },
                { value: 'queue_depth', label: '队列堆积（由调度器侧触发）' },
              ]}
            />
          </Form.Item>

          <Form.Item
            name="threshold"
            label="阈值"
            tooltip="连续失败：失败次数；结果下降：下降百分比；任务超时：分钟数"
            rules={[{ required: true, message: '请输入阈值' }]}
          >
            <InputNumber min={0} style={{ width: '100%' }} placeholder="根据规则类型填写" />
          </Form.Item>

          <Form.Item
            name="window_minutes"
            label="静默窗口（分钟）"
            initialValue={60}
            tooltip="触发后在此窗口内不再重复告警"
          >
            <InputNumber min={1} max={1440} style={{ width: '100%' }} />
          </Form.Item>

          <Form.Item
            name="severity"
            label="严重度"
            initialValue="warning"
          >
            <Select
              options={[
                { value: 'info', label: '信息' },
                { value: 'warning', label: '警告' },
                { value: 'critical', label: '严重' },
              ]}
            />
          </Form.Item>

          <Form.Item
            name="enabled"
            label="启用状态"
            initialValue={true}
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}
