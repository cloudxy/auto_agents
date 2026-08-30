/**
 * ScheduleTab - 定时任务管理（列表 + 创建/编辑/启停/删除）
 */
import React, { useCallback, useEffect, useState } from 'react'
import {
  Table, Button, Space, Modal, Form, Select, Input, Switch, Popconfirm,
  Empty, Typography, message,
} from 'antd'
import { PlusOutlined, ReloadOutlined, PlayCircleOutlined, DeleteOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  fetchSchedules, createSchedule, updateSchedule, deleteSchedule,
} from '../../services/spiders'
import { renderParamFields, collectParams } from './formUtils'
import type { SpiderRegistry, SpiderMap } from './types'
import type { SpiderSchedule as SpiderScheduleType } from '../../services/spiders'
import { apiErrorMessage, isFormValidateError } from '../../utils/errorMessage'

const { Text } = Typography

export interface ScheduleTabProps {
  registry: SpiderRegistry
  spiderMap: SpiderMap
  canCreate: boolean
  canSchedule: boolean
  onRunTask: (spiderName: string) => void
}

export const ScheduleTab: React.FC<ScheduleTabProps> = ({
  registry, spiderMap, canCreate, canSchedule, onRunTask,
}) => {
  const [schedules, setSchedules] = useState<SpiderScheduleType[]>([])
  const [modalOpen, setModalOpen] = useState(false)
  const [scheduleSpider, setScheduleSpider] = useState<string | undefined>(undefined)
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm()
  const [scheduleStrategy, setScheduleStrategy] = useState<string>('static')

  const loadSchedules = useCallback(async () => {
    try {
      const res = await fetchSchedules()
      setSchedules(res.items || [])
    } catch (error) {
      message.error('获取定时任务失败')
    }
  }, [])

  useEffect(() => {
    loadSchedules()
  }, [loadSchedules])

  const scheduleSpiderType = scheduleSpider ? spiderMap[scheduleSpider]?.type : undefined
  const scheduleTypeFields = registry.types.find((t) => t.type === scheduleSpiderType)?.fields

  const openModal = () => {
    form.resetFields()
    setScheduleSpider(undefined)
    setScheduleStrategy('static')
    setModalOpen(true)
  }

  const onSubmitSchedule = async () => {
    try {
      const values = await form.validateFields()
      const collected = collectParams(values, scheduleTypeFields)
      if (typeof collected === 'string') {
        message.error(collected)
        return
      }
      const strategy = values._strategy || 'static'
      if (strategy !== 'static') {
        collected._strategy = strategy
      }
      if (strategy === 'quiet' && values._quiet_hours) {
        collected._quiet_hours = String(values._quiet_hours).split(',').map((s: string) => s.trim()).filter(Boolean)
      }
      setSubmitting(true)
      await createSchedule({
        spider_name: values.spider_name,
        cron_expr: values.cron_expr.trim(),
        params: Object.keys(collected).length ? JSON.stringify(collected) : null,
        enabled: true,
      })
      message.success('定时任务已创建')
      setModalOpen(false)
      loadSchedules()
    } catch (error) {
      if (isFormValidateError(error)) return
      message.error(apiErrorMessage(error, '创建定时任务失败'))
    } finally {
      setSubmitting(false)
    }
  }

  const onToggleSchedule = async (schedule: SpiderScheduleType, enabled: boolean) => {
    try {
      await updateSchedule(schedule.id, { enabled })
      message.success(enabled ? '定时任务已启用' : '定时任务已停用')
      loadSchedules()
    } catch (error) {
      message.error(apiErrorMessage(error, '操作失败'))
    }
  }

  const onDeleteSchedule = async (schedule: SpiderScheduleType) => {
    try {
      await deleteSchedule(schedule.id)
      message.success(`定时任务已删除（${spiderMap[schedule.spider_name]?.title || schedule.spider_name}）`)
      loadSchedules()
    } catch (error) {
      message.error(apiErrorMessage(error, '删除失败'))
    }
  }

  const columns: ColumnsType<SpiderScheduleType> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 70 },
    {
      title: '爬虫',
      dataIndex: 'spider_name',
      key: 'spider_name',
      render: (name: string) => (
        <Space direction="vertical" size={0}>
          <Text strong>{spiderMap[name]?.title || name}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{name}</Text>
        </Space>
      ),
    },
    {
      title: 'Cron 表达式',
      dataIndex: 'cron_expr',
      key: 'cron_expr',
      width: 160,
      render: (expr: string) => <Text code>{expr}</Text>,
    },
    { title: '上次触发', dataIndex: 'last_run_at', key: 'last_run_at', width: 180, render: (v: string | null) => v || '-' },
    { title: '下次触发', dataIndex: 'next_run_at', key: 'next_run_at', width: 180, render: (v: string | null) => v || '-' },
    {
      title: '启用',
      dataIndex: 'enabled',
      key: 'enabled',
      width: 90,
      render: (enabled: boolean, record: SpiderScheduleType) => (
        <Switch checked={enabled} size="small" disabled={!canSchedule} onChange={(v) => onToggleSchedule(record, v)} />
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 140,
      render: (_: unknown, record: SpiderScheduleType) => (
        <Space size="small">
          {canCreate && (
            <Button type="link" size="small" icon={<PlayCircleOutlined />} onClick={() => onRunTask(record.spider_name)}>
              手动运行
            </Button>
          )}
          {canSchedule && (
            <Popconfirm
              title="确认删除该定时任务？"
              okText="删除"
              okButtonProps={{ danger: true }}
              cancelText="取消"
              onConfirm={() => onDeleteSchedule(record)}
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
      <div style={{ marginBottom: 16, textAlign: 'right' }}>
        <Space>
          {canSchedule && (
            <Button type="primary" icon={<PlusOutlined />} onClick={openModal}>
              新建定时任务
            </Button>
          )}
          <Button icon={<ReloadOutlined />} onClick={loadSchedules}>刷新</Button>
        </Space>
      </div>
      <Table
        columns={columns}
        dataSource={schedules}
        rowKey="id"
        pagination={false}
        locale={{ emptyText: <Empty description="暂无定时任务" /> }}
      />

      <Modal
        title="新建定时任务"
        open={modalOpen}
        onOk={onSubmitSchedule}
        onCancel={() => setModalOpen(false)}
        confirmLoading={submitting}
        okText="创建"
        destroyOnHidden
        width={560}
      >
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item
            name="spider_name"
            label="选择爬虫"
            rules={[{ required: true, message: '请选择爬虫' }]}
          >
            <Select
              placeholder="选择要定时运行的爬虫"
              onChange={(v) => setScheduleSpider(v)}
              options={registry.spiders.map((s) => ({
                label: `${s.title}（${s.name}）`,
                value: s.name,
              }))}
            />
          </Form.Item>

          <Form.Item
            name="cron_expr"
            label="Cron 表达式"
            tooltip="5 段标准格式：分 时 日 月 周"
            rules={[
              { required: true, message: '请填写 Cron 表达式' },
              {
                pattern: /^(\S+\s+){4}\S+$/,
                message: '需为 5 段 Cron 表达式，如 */5 * * * *',
              },
            ]}
          >
            <Input placeholder="如 */5 * * * *（每 5 分钟）、0 8 * * 1-5（工作日 8 点）" />
          </Form.Item>

          <Form.Item
            name="_strategy"
            label="调度策略"
            initialValue="static"
            tooltip="静态：固定优先级；动态优先级：系统根据历史成功率/时长自动调整；时段感知：静默时段内自动延迟触发"
          >
            <Select
              onChange={(v) => setScheduleStrategy(v)}
              options={[
                { value: 'static', label: '静态（默认）' },
                { value: 'dynamic', label: '动态优先级' },
                { value: 'quiet', label: '时段感知' },
              ]}
            />
          </Form.Item>

          {scheduleStrategy === 'dynamic' && (
            <div style={{ marginBottom: 16, padding: '8px 12px', background: '#f6ffed', borderRadius: 6, border: '1px solid #b7eb8f' }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                系统将根据历史成功率/运行时长自动调整任务优先级：成功率低于阈值时降低优先级，运行时间超过阈值时提高优先级。
              </Text>
            </div>
          )}

          {scheduleStrategy === 'quiet' && (
            <Form.Item
              name="_quiet_hours"
              label="静默时段"
              tooltip="格式：HH:MM-HH:MM，多个用逗号分隔，如 02:00-06:00,23:00-23:59"
            >
              <Input placeholder="如 02:00-06:00,23:00-23:59（静默期内非高优先级任务将延迟触发）" />
            </Form.Item>
          )}

          {renderParamFields(scheduleTypeFields)}
        </Form>
      </Modal>
    </>
  )
}
