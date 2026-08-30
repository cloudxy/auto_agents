/**
 * AI 采集页面 - 三步向导（创建规划 → 方案预览 → 试采上线）+ 方案列表
 *
 * 向导流程：
 * ① 粘贴目标链接（可选粘贴 HTML 片段降级离线规划）→ 创建计划并自动触发 LLM 规划，轮询至 draft/failed
 * ② 方案预览：plan_json.flow 结构可视化 + 关键字段本地可调（selectors/max_pages/filters），
 *    可重新规划；试采走服务端方案（含自动修复迭代），调整后的方案可直接以 flow_generic 试跑
 * ③ 试采结果对比：test_history 各轮结果 + 试采任务日志/结果抽屉 → 最近一次通过后一键上线注册
 *
 * 轮询模式沿用全局约定：2.5s 间隔，仅 planning/testing（未通过）状态轮询。
 */
import React, { useCallback, useEffect, useState } from 'react'
import {
  Alert, Button, Card, Collapse, Descriptions, Empty, Form, Input, InputNumber,
  Popconfirm, Select, Space, Steps, Table, Tabs, Tag, Typography, message,
} from 'antd'
import {
  PlusOutlined, DeleteOutlined, ReloadOutlined, RocketOutlined,
  ExperimentOutlined, EditOutlined, FileTextOutlined, EyeOutlined,
  ThunderboltOutlined, CheckCircleOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  AI_PLAN_STATUS_META, AI_PLAN_STATUS_OPTIONS, isPlanPolling, isLatestTestPassed,
  createAiPlan, fetchAiPlans, fetchAiPlan, triggerAiPlan, triggerAiTest,
  registerAiPlan, deleteAiPlan,
} from '../services/ai'
import type { AiPlan, AiPlanTestHistory, FlowConfig, FlowSelector } from '../services/ai'
import { fetchTaskLogs, runSpider } from '../services/spiders'
import { SelectorRowList } from '../components/spider/formUtils'
import { LogDrawer } from '../components/spider/LogDrawer'
import { ResultDrawer } from '../components/spider/ResultDrawer'
import { STATUS_META } from '../components/spider/types'
import type { Task, SpiderMap } from '../components/spider/types'
import { usePermission } from '../hooks/usePermission'

const { Text } = Typography

const SELECTOR_TYPE_COLORS: Record<string, string> = { css: 'cyan', xpath: 'purple', regex: 'orange' }
const FILTER_OP_LABELS: Record<string, string> = { contains: '包含', equals: '等于', regex: '正则' }

/** 试采/日志抽屉用的爬虫映射（flow_generic 为流程化引擎） */
const PSEUDO_SPIDER_MAP: SpiderMap = { flow_generic: { title: '流程化采集', type: 'flow' } }

/** 伪 Task（复用 LogDrawer/ResultDrawer：仅依赖 id/spider_name/status） */
const pseudoTask = (taskId: number, status: string, resultCount = 0): Task => ({
  id: taskId,
  spider_name: 'flow_generic',
  status,
  priority: 'low',
  result_count: resultCount,
})

// ----------------------------------------------------------------------
// 展示组件：选择器规则表
// ----------------------------------------------------------------------
const SelectorTable: React.FC<{ rows: FlowSelector[]; title: string }> = ({ rows, title }) => (
  <div style={{ marginBottom: 12 }}>
    <Text type="secondary" style={{ display: 'block', marginBottom: 6 }}>{title}</Text>
    <Table
      size="small"
      dataSource={rows}
      rowKey={(_, index) => String(index)}
      pagination={false}
      columns={[
        { title: '字段名', dataIndex: 'name', width: 140, render: (v: string) => <Text code>{v}</Text> },
        {
          title: '类型', dataIndex: 'type', width: 90,
          render: (v: string) => <Tag color={SELECTOR_TYPE_COLORS[v] || 'default'}>{v}</Tag>,
        },
        { title: '表达式', dataIndex: 'expr', render: (v: string) => <Text code style={{ fontSize: 12 }}>{v}</Text> },
      ]}
    />
  </div>
)

// ----------------------------------------------------------------------
// 展示组件：flow 结构可视化
// ----------------------------------------------------------------------
const FlowPreview: React.FC<{ flow: FlowConfig }> = ({ flow }) => (
  <div>
    <Descriptions size="small" column={2} bordered style={{ marginBottom: 12 }}>
      <Descriptions.Item label="自动翻页">
        {flow.pagination
          ? `${flow.pagination.max_pages} 页 · ${flow.pagination.type}：${flow.pagination.selector}`
          : '未配置'}
      </Descriptions.Item>
      <Descriptions.Item label="详情页采集">
        {flow.detail
          ? `列表项 ${flow.detail.list_selector} → 链接 ${flow.detail.url_selector}`
          : '未配置'}
      </Descriptions.Item>
      <Descriptions.Item label="JS 渲染">{flow.render_js ? '启用（Playwright）' : '关闭'}</Descriptions.Item>
      <Descriptions.Item label="过滤条件">{flow.filters?.length || 0} 条</Descriptions.Item>
    </Descriptions>
    <SelectorTable rows={flow.selectors || []} title="列表页提取规则" />
    {flow.detail && flow.detail.selectors && flow.detail.selectors.length > 0 && (
      <SelectorTable rows={flow.detail.selectors} title="详情页提取规则" />
    )}
    {flow.filters && flow.filters.length > 0 && (
      <div style={{ marginBottom: 12 }}>
        <Text type="secondary" style={{ display: 'block', marginBottom: 6 }}>条件过滤</Text>
        <Space wrap>
          {flow.filters.map((f, i) => (
            <Tag key={i} color="blue">
              {f.field} {FILTER_OP_LABELS[f.op] || f.op} 「{f.value}」
            </Tag>
          ))}
        </Space>
      </div>
    )}
  </div>
)

// ----------------------------------------------------------------------
// 编辑组件：过滤条件行（字段/操作符/值）
// ----------------------------------------------------------------------
const FilterRuleList: React.FC = () => (
  <Form.List name="filters">
    {(rows, { add, remove }) => (
      <>
        {rows.map(({ key, name: rowName, ...rest }) => (
          <Space key={key} align="baseline" style={{ display: 'flex', marginBottom: 4 }}>
            <Form.Item {...rest} name={[rowName, 'field']} noStyle
              rules={[{ required: true, message: '字段名必填' }]}>
              <Input placeholder="字段名，如 title" style={{ width: 130 }} />
            </Form.Item>
            <Form.Item {...rest} name={[rowName, 'op']} noStyle initialValue="contains">
              <Select style={{ width: 90 }} options={[
                { value: 'contains', label: '包含' },
                { value: 'equals', label: '等于' },
                { value: 'regex', label: '正则' },
              ]} />
            </Form.Item>
            <Form.Item {...rest} name={[rowName, 'value']} noStyle
              rules={[{ required: true, message: '值必填' }]}>
              <Input placeholder="匹配值，如 Python" style={{ width: 220 }} />
            </Form.Item>
            <DeleteOutlined onClick={() => remove(rowName)} />
          </Space>
        ))}
        <Button type="dashed" block icon={<PlusOutlined />} onClick={() => add({ op: 'contains' })}>
          添加过滤条件
        </Button>
      </>
    )}
  </Form.List>
)

// ----------------------------------------------------------------------
// 主页面
// ----------------------------------------------------------------------
const AiPlans: React.FC = () => {
  const { hasPermission } = usePermission()
  const canOperate = hasPermission('btn:create') // 规划/试采/上线与创建共享 operator 权限
  const canDelete = hasPermission('btn:delete')  // 删除计划仅 admin

  // 向导状态
  const [step, setStep] = useState(0)
  const [plan, setPlan] = useState<AiPlan | null>(null)
  const [creating, setCreating] = useState(false)
  const [actionLoading, setActionLoading] = useState('')
  const [editedFlow, setEditedFlow] = useState<FlowConfig | null>(null)
  const [createForm] = Form.useForm()
  const [flowForm] = Form.useForm()

  // 调整方案直跑的试采任务
  const [customTask, setCustomTask] = useState<Task | null>(null)

  // 日志/结果抽屉
  const [logTask, setLogTask] = useState<Task | null>(null)
  const [resultTask, setResultTask] = useState<Task | null>(null)

  // 方案列表状态
  const [plans, setPlans] = useState<AiPlan[]>([])
  const [planTotal, setPlanTotal] = useState(0)
  const [planPage, setPlanPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined)
  const [listLoading, setListLoading] = useState(false)
  const [activeTab, setActiveTab] = useState('wizard')

  const flow = plan?.plan_json?.flow || null
  const history: AiPlanTestHistory[] = plan?.plan_json?.test_history || []
  const latestPassed = isLatestTestPassed(plan)

  // ---------------- 方案列表 ----------------
  const loadPlans = useCallback(async (showSpin = true) => {
    if (showSpin) setListLoading(true)
    try {
      const res = await fetchAiPlans({ skip: (planPage - 1) * 20, limit: 20, status: statusFilter })
      setPlans(res.items || [])
      setPlanTotal(res.total || 0)
    } catch (error) {
      message.error('获取 AI 方案列表失败')
    } finally {
      if (showSpin) setListLoading(false)
    }
  }, [planPage, statusFilter])

  useEffect(() => {
    loadPlans()
  }, [loadPlans])

  // ---------------- 计划状态轮询（2.5s，仅进行中）----------------
  useEffect(() => {
    if (!plan || !isPlanPolling(plan)) return
    const planId = plan.id
    const timer = setInterval(async () => {
      try {
        const fresh = await fetchAiPlan(planId)
        setPlan(fresh)
        if (fresh.status === 'testing' || fresh.status === 'registered') {
          setStep((s) => (s < 2 ? 2 : s))
        }
      } catch (error) { /* 轮询静默失败 */ }
    }, 2500)
    return () => clearInterval(timer)
  }, [plan])

  // ---------------- 调整方案试采任务状态轮询（3s，仅进行中）----------------
  useEffect(() => {
    if (!customTask || !(customTask.status === 'pending' || customTask.status === 'running')) return
    const taskId = customTask.id
    const timer = setInterval(() => {
      fetchTaskLogs(taskId, 5)
        .then((data) => setCustomTask((prev) => (prev && prev.id === taskId ? { ...prev, status: data.status } : prev)))
        .catch(() => { /* 静默 */ })
    }, 3000)
    return () => clearInterval(timer)
  }, [customTask])

  // ---------------- 服务端 flow 变化时同步本地编辑表单 ----------------
  useEffect(() => {
    if (flow) {
      setEditedFlow(flow)
      flowForm.setFieldsValue({
        selectors: flow.selectors || [],
        pagination: flow.pagination || { type: 'css', max_pages: 2 },
        detail: flow.detail || {},
        detail_selectors: flow.detail?.selectors || [],
        filters: flow.filters || [],
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plan?.id, plan?.updated_at])

  // ---------------- 向导动作 ----------------
  const onCreate = async () => {
    try {
      const values = await createForm.validateFields()
      setCreating(true)
      const created = await createAiPlan({
        target_url: values.target_url.trim(),
        ...(values.html_snippet ? { html_snippet: values.html_snippet } : {}),
      })
      setPlan(created)
      setStep(1)
      // 创建后立即触发规划（后台执行，轮询推进状态机）
      const snapshot = await triggerAiPlan(created.id)
      setPlan(snapshot)
      message.success(`计划 #${created.id} 已创建，LLM 正在规划采集方案`)
    } catch (error: any) {
      if (error?.errorFields) return
      message.error(error?.response?.data?.message || '创建计划失败')
    } finally {
      setCreating(false)
    }
  }

  const resetWizard = () => {
    setPlan(null)
    setStep(0)
    setEditedFlow(null)
    setCustomTask(null)
    createForm.resetFields()
    flowForm.resetFields()
  }

  const onReplan = async () => {
    if (!plan) return
    try {
      setActionLoading('plan')
      const snapshot = await triggerAiPlan(plan.id)
      setPlan(snapshot)
      setEditedFlow(null)
      setStep(1)
      message.success('已重新触发规划')
    } catch (error: any) {
      message.error(error?.response?.data?.message || '触发规划失败')
    } finally {
      setActionLoading('')
    }
  }

  const onTest = async () => {
    if (!plan) return
    try {
      setActionLoading('test')
      const snapshot = await triggerAiTest(plan.id)
      setPlan(snapshot)
      setStep(2)
      message.success('试采任务已提交（失败将自动修复迭代重试）')
    } catch (error: any) {
      message.error(error?.response?.data?.message || '触发试采失败')
    } finally {
      setActionLoading('')
    }
  }

  // 用本地调整后的 flow 直接提交 flow_generic 试跑（不改动服务端方案）
  const onTestEdited = async () => {
    if (!plan || !editedFlow) return
    try {
      setActionLoading('test_edited')
      const params: Record<string, unknown> = {
        urls: [plan.target_url],
        selectors: editedFlow.selectors,
      }
      if (editedFlow.pagination) params.pagination = editedFlow.pagination
      if (editedFlow.detail) params.detail = editedFlow.detail
      if (editedFlow.filters && editedFlow.filters.length) params.filters = editedFlow.filters
      if (editedFlow.render_js) params.render_js = true
      if (editedFlow.wait_for) params.wait_for = editedFlow.wait_for
      if (editedFlow.wait_timeout) params.wait_timeout = editedFlow.wait_timeout
      const task = await runSpider('flow_generic', JSON.stringify(params), 'low')
      setCustomTask(task)
      setStep(2)
      message.success(`已用调整后的方案提交试采任务 #${task.id}`)
    } catch (error: any) {
      message.error(error?.response?.data?.message || '提交试采失败')
    } finally {
      setActionLoading('')
    }
  }

  const onApplyFlowEdit = async () => {
    try {
      const values = await flowForm.validateFields()
      const rows = Array.isArray(values.selectors) ? values.selectors : []
      const selectors = rows
        .filter((r: any) => r && String(r.name || '').trim() && String(r.expr || '').trim())
        .map((r: any) => ({ name: String(r.name).trim(), type: r.type || 'css', expr: String(r.expr).trim() }))
      if (!selectors.length) {
        message.error('请至少保留一条提取规则')
        return
      }
      const p = values.pagination || {}
      const pagination = String(p.selector || '').trim()
        ? { selector: String(p.selector).trim(), type: p.type || 'css', max_pages: Number(p.max_pages) || 2 }
        : null
      const d = values.detail || {}
      const detailSelectors = (Array.isArray(values.detail_selectors) ? values.detail_selectors : [])
        .filter((r: any) => r && String(r.name || '').trim() && String(r.expr || '').trim())
        .map((r: any) => ({ name: String(r.name).trim(), type: r.type || 'css', expr: String(r.expr).trim() }))
      const detail = String(d.list_selector || '').trim() && String(d.url_selector || '').trim()
        ? {
            list_selector: String(d.list_selector).trim(),
            url_selector: String(d.url_selector).trim(),
            selectors: detailSelectors,
          }
        : null
      const filters = (Array.isArray(values.filters) ? values.filters : [])
        .filter((r: any) => r && String(r.field || '').trim() && String(r.value || '').trim())
        .map((r: any) => ({ field: String(r.field).trim(), op: r.op || 'contains', value: String(r.value).trim() }))
      setEditedFlow({
        selectors,
        pagination,
        detail,
        filters,
        render_js: !!flow?.render_js,
        wait_for: flow?.wait_for || null,
        wait_timeout: flow?.wait_timeout || null,
      })
      message.success('已应用调整（本地预览；可点击「试采调整后方案」验证）')
    } catch (error) { /* 表单校验失败 */ }
  }

  const onRegister = async () => {
    if (!plan) return
    try {
      setActionLoading('register')
      const snapshot = await registerAiPlan(plan.id)
      setPlan(snapshot)
      message.success(`已上线为爬虫定义：${snapshot.plan_json?.registered_definition || '-'}（类型 flow）`)
    } catch (error: any) {
      message.error(error?.response?.data?.message || '上线失败')
    } finally {
      setActionLoading('')
    }
  }

  // 从列表载入计划到向导
  const openPlanInWizard = (p: AiPlan) => {
    setPlan(p)
    setEditedFlow(null)
    setCustomTask(null)
    const hist = p.plan_json?.test_history || []
    if (p.status === 'testing' || p.status === 'registered' || (p.status === 'failed' && hist.length > 0)) {
      setStep(2)
    } else {
      setStep(1)
    }
    setActiveTab('wizard')
  }

  const onDeletePlan = async (p: AiPlan) => {
    try {
      await deleteAiPlan(p.id)
      message.success(`计划 #${p.id} 已删除`)
      loadPlans(false)
    } catch (error: any) {
      message.error(error?.response?.data?.message || '删除失败')
    }
  }

  // ---------------- 方案列表列 ----------------
  const planColumns: ColumnsType<AiPlan> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 70 },
    {
      title: '目标链接', dataIndex: 'target_url', key: 'target_url', ellipsis: true,
      render: (v: string) => <a href={v} target="_blank" rel="noreferrer">{v}</a>,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 110,
      render: (status: string) => {
        const meta = AI_PLAN_STATUS_META[status] || { label: status, color: 'default' }
        return <Tag color={meta.color}>{meta.label}</Tag>
      },
    },
    { title: '修复迭代', dataIndex: 'iteration_count', key: 'iteration_count', width: 90, align: 'center' },
    {
      title: '试采任务', dataIndex: 'test_task_id', key: 'test_task_id', width: 90,
      render: (v: number | null) => (v ? `#${v}` : '-'),
    },
    {
      title: '注册定义', key: 'registered', width: 180, ellipsis: true,
      render: (_: any, record: AiPlan) => (
        record.plan_json?.registered_definition
          ? <Text code style={{ fontSize: 12 }}>{record.plan_json.registered_definition}</Text>
          : '-'
      ),
    },
    { title: '创建人', dataIndex: 'created_by', key: 'created_by', width: 100, render: (v: string | null) => v || '-' },
    { title: '更新时间', dataIndex: 'updated_at', key: 'updated_at', width: 170, render: (v: string | null) => v || '-' },
    {
      title: '操作', key: 'action', width: 150,
      render: (_: any, record: AiPlan) => (
        <Space size="small">
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openPlanInWizard(record)}>
            继续
          </Button>
          {canDelete && (
            <Popconfirm
              title="确认删除该计划？"
              description="规划/试采进行中时后端将拒绝删除。"
              okText="删除"
              okButtonProps={{ danger: true }}
              cancelText="取消"
              onConfirm={() => onDeletePlan(record)}
            >
              <Button type="link" danger size="small" icon={<DeleteOutlined />}>删除</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  // ---------------- 试采历史列 ----------------
  const historyColumns: ColumnsType<AiPlanTestHistory> = [
    { title: '轮次', dataIndex: 'iteration', key: 'iteration', width: 70, render: (v: number) => `第 ${v + 1} 轮` },
    { title: '任务', dataIndex: 'task_id', key: 'task_id', width: 80, render: (v: number) => `#${v}` },
    {
      title: '任务状态', dataIndex: 'status', key: 'status', width: 100,
      render: (v: string) => {
        const meta = STATUS_META[v] || { label: v, color: 'default' }
        return <Tag color={meta.color}>{meta.label}</Tag>
      },
    },
    { title: '结果条数', dataIndex: 'result_count', key: 'result_count', width: 90, align: 'center' },
    {
      title: '判定', dataIndex: 'passed', key: 'passed', width: 90,
      render: (passed: boolean) => passed
        ? <Tag color="success" icon={<CheckCircleOutlined />}>通过</Tag>
        : <Tag color="error">未通过</Tag>,
    },
    { title: '说明', dataIndex: 'reason', key: 'reason', ellipsis: true },
  ]

  // ---------------- 渲染：向导步骤内容 ----------------
  const renderStep0 = () => (
    <Form form={createForm} layout="vertical" style={{ maxWidth: 640 }}>
      <Alert
        type="info" showIcon style={{ marginBottom: 16 }}
        message="粘贴目标页面链接，LLM 将自动规划采集规则（selectors / 翻页 / 详情页 / 过滤）"
        description="页面无法直接访问时可粘贴 HTML 片段，规划将降级使用该片段（离线规划）。"
      />
      <Form.Item
        name="target_url" label="目标页面链接"
        validateTrigger="onBlur"
        rules={[
          { required: true, message: '请输入目标页面链接' },
          { pattern: /^https?:\/\//, message: '必须是 http(s) 地址' },
        ]}
      >
        <Input placeholder="https://example.com/news/list" allowClear />
      </Form.Item>
      <Form.Item
        name="html_snippet" label="HTML 片段（可选）"
        tooltip="可选；预置后规划阶段不再在线抓取，适合需要登录或反爬严格的页面"
      >
        <Input.TextArea rows={6} placeholder="粘贴目标页面的 HTML 片段（最多 200000 字符）" />
      </Form.Item>
      {canOperate && (
        <Button type="primary" icon={<ThunderboltOutlined />} loading={creating} onClick={onCreate}>
          创建并开始规划
        </Button>
      )}
    </Form>
  )

  const renderStep1 = () => {
    if (!plan) return null
    return (
      <div style={{ maxWidth: 860 }}>
        {plan.status === 'planning' && (
          <Alert
            type="info" showIcon style={{ marginBottom: 16 }}
            message={`计划 #${plan.id} 正在通过 LLM 规划采集方案...（每 2.5 秒自动刷新）`}
          />
        )}
        {plan.status === 'failed' && (
          <Alert
            type="error" showIcon style={{ marginBottom: 16 }}
            message="规划失败"
            description={plan.error_message || '未知错误'}
          />
        )}
        {plan.status === 'draft' && !flow && (
          <Alert
            type="warning" showIcon style={{ marginBottom: 16 }}
            message="方案尚未生成"
            description="该计划还没有规划产物，可点击「重新规划」触发 LLM 规划。"
          />
        )}
        {flow && <FlowPreview flow={flow} />}
        {flow && canOperate && (
          <Collapse
            size="small"
            style={{ marginBottom: 16 }}
            items={[{
              key: 'edit',
              label: '微调方案（本地预览，可直跑验证）',
              children: (
                <Form form={flowForm} layout="vertical">
                  <Form.Item label="列表页提取规则" required tooltip="字段名 + 选择器类型（xpath/css/regex）+ 表达式">
                    <SelectorRowList name="selectors" />
                  </Form.Item>
                  <Form.Item label="分页设置">
                    <Collapse size="small" items={[{
                      key: 'pagination',
                      label: '自动翻页（留空选择器表示不翻页）',
                      children: (
                        <>
                          <Form.Item name={['pagination', 'selector']} label="下一页选择器" style={{ marginBottom: 8 }}>
                            <Input placeholder="如 a.next" />
                          </Form.Item>
                          <Form.Item name={['pagination', 'type']} label="选择器类型" style={{ marginBottom: 8 }}>
                            <Select options={[
                              { value: 'css', label: 'CSS' },
                              { value: 'xpath', label: 'XPath' },
                            ]} />
                          </Form.Item>
                          <Form.Item name={['pagination', 'max_pages']} label="最大页数" style={{ marginBottom: 0 }}>
                            <InputNumber min={1} max={100} />
                          </Form.Item>
                        </>
                      ),
                    }]} />
                  </Form.Item>
                  <Form.Item label="详情页设置">
                    <Collapse size="small" items={[{
                      key: 'detail',
                      label: '详情页二次采集（两项都填才生效）',
                      children: (
                        <>
                          <Form.Item name={['detail', 'list_selector']} label="列表项选择器（css）" style={{ marginBottom: 8 }}>
                            <Input placeholder="如 li.news" />
                          </Form.Item>
                          <Form.Item name={['detail', 'url_selector']} label="链接选择器（xpath）" style={{ marginBottom: 8 }}>
                            <Input placeholder="如 .//a/@href" />
                          </Form.Item>
                          <Form.Item label="详情页提取规则" style={{ marginBottom: 0 }}>
                            <SelectorRowList name="detail_selectors" addLabel="添加详情字段规则" />
                          </Form.Item>
                        </>
                      ),
                    }]} />
                  </Form.Item>
                  <Form.Item label="条件过滤">
                    <FilterRuleList />
                  </Form.Item>
                  <Button icon={<CheckCircleOutlined />} onClick={onApplyFlowEdit}>应用调整</Button>
                </Form>
              ),
            }]} />
        )}
        {canOperate && (
          <Space wrap>
            <Button
              icon={<ReloadOutlined />} loading={actionLoading === 'plan'}
              disabled={plan.status === 'planning'}
              onClick={onReplan}
            >
              重新规划
            </Button>
            {flow && (
              <Button
                type="primary" icon={<ExperimentOutlined />}
                loading={actionLoading === 'test'}
                disabled={plan.status === 'planning'}
                onClick={onTest}
              >
                试采（服务端方案）
              </Button>
            )}
            {flow && editedFlow && (
              <Button
                icon={<ThunderboltOutlined />} loading={actionLoading === 'test_edited'}
                disabled={plan.status === 'planning'}
                onClick={onTestEdited}
              >
                试采调整后方案
              </Button>
            )}
          </Space>
        )}
      </div>
    )
  }

  const renderStep2 = () => {
    if (!plan) return null
    const testing = plan.status === 'testing'
    return (
      <div style={{ maxWidth: 860 }}>
        {plan.status === 'registered' && (
          <Alert
            type="success" showIcon style={{ marginBottom: 16 }}
            message={`已上线为爬虫定义：${plan.plan_json?.registered_definition || '-'}`}
            description="可在「爬虫管理 → 任务列表」中选择该 flow 类型爬虫发起正式采集。"
          />
        )}
        {testing && latestPassed && (
          <Alert
            type="success" showIcon style={{ marginBottom: 16 }}
            message="最近一次试采通过，可一键上线注册为 flow 类型爬虫定义"
          />
        )}
        {testing && !latestPassed && (
          <Alert
            type="info" showIcon style={{ marginBottom: 16 }}
            message={`试采进行中（第 ${(plan.iteration_count || 0) + 1} 轮，失败将自动修复迭代）...每 2.5 秒自动刷新`}
          />
        )}
        {plan.status === 'failed' && (
          <Alert
            type="error" showIcon style={{ marginBottom: 16 }}
            message="试采未通过（自动修复迭代已达上限）"
            description={plan.error_message || '可回到方案预览调整后重试'}
          />
        )}
        {history.length > 0 ? (
          <>
            <Text type="secondary" style={{ display: 'block', marginBottom: 6 }}>试采历史（各轮结果对比）</Text>
            <Table
              size="small"
              dataSource={history}
              rowKey={(record) => `${record.iteration}-${record.task_id}`}
              pagination={false}
              columns={historyColumns}
              style={{ marginBottom: 16 }}
            />
          </>
        ) : (
          <Empty description="暂无试采记录（试采启动后展示各轮结果）" style={{ marginBottom: 16 }} />
        )}
        {canOperate && (
          <Space wrap>
            <Button
              type="primary" icon={<RocketOutlined />}
              loading={actionLoading === 'register'}
              disabled={!latestPassed || plan.status === 'planning' || plan.status === 'registered'}
              onClick={onRegister}
            >
              一键上线注册
            </Button>
            <Button
              icon={<ExperimentOutlined />} loading={actionLoading === 'test'}
              disabled={plan.status === 'planning' || plan.status === 'registered'}
              onClick={onTest}
            >
              重新试采
            </Button>
            <Button icon={<EditOutlined />} onClick={() => setStep(1)}>返回方案预览</Button>
          </Space>
        )}
        {plan.test_task_id && (
          <div style={{ marginTop: 12 }}>
            <Text type="secondary" style={{ marginRight: 8 }}>
              最近试采任务 #{plan.test_task_id}：
            </Text>
            <Space>
              <Button
                type="link" size="small" icon={<FileTextOutlined />}
                onClick={() => setLogTask(pseudoTask(plan.test_task_id!, 'running'))}
              >
                查看日志
              </Button>
              <Button
                type="link" size="small" icon={<EyeOutlined />}
                onClick={() => setResultsTaskWithCount(plan)}
              >
                查看结果
              </Button>
            </Space>
          </div>
        )}
        {customTask && (
          <div style={{ marginTop: 8 }}>
            <Space>
              <Text type="secondary">调整方案试采任务 #{customTask.id}：</Text>
              <Tag color={STATUS_META[customTask.status]?.color || 'default'}>
                {STATUS_META[customTask.status]?.label || customTask.status}
              </Tag>
              <Button
                type="link" size="small" icon={<FileTextOutlined />}
                onClick={() => setLogTask(pseudoTask(customTask.id, customTask.status))}
              >
                查看日志
              </Button>
              <Button
                type="link" size="small" icon={<EyeOutlined />}
                onClick={() => setResultTask(pseudoTask(customTask.id, customTask.status))}
              >
                查看结果
              </Button>
            </Space>
          </div>
        )}
      </div>
    )
  }

  // 带最近试采结果条数打开结果抽屉
  const setResultsTaskWithCount = (p: AiPlan) => {
    const last = (p.plan_json?.test_history || []).slice(-1)[0]
    setResultTask(pseudoTask(p.test_task_id!, p.status === 'registered' ? 'completed' : 'running', last?.result_count || 0))
  }

  const stepItems = [
    { title: '创建计划' },
    { title: '方案预览与调整' },
    { title: '试采与上线' },
  ]

  return (
    <Card
      title="AI 采集"
      extra={
        <Button icon={<PlusOutlined />} onClick={() => { resetWizard(); setActiveTab('wizard') }}>
          新建采集计划
        </Button>
      }
    >
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: 'wizard',
            label: '采集向导',
            children: (
              <>
                <Steps current={step} items={stepItems} style={{ marginBottom: 24, maxWidth: 860 }} />
                {step > 0 && plan && (
                  <div style={{ marginBottom: 16 }}>
                    <Space wrap>
                      <Tag color="blue">计划 #{plan.id}</Tag>
                      <Text type="secondary" style={{ maxWidth: 480 }} ellipsis>{plan.target_url}</Text>
                      <Tag color={(AI_PLAN_STATUS_META[plan.status] || { color: 'default' }).color}>
                        {(AI_PLAN_STATUS_META[plan.status] || { label: plan.status }).label}
                      </Tag>
                      <Button type="link" size="small" onClick={resetWizard}>重置向导</Button>
                    </Space>
                  </div>
                )}
                {step === 0 && renderStep0()}
                {step === 1 && renderStep1()}
                {step === 2 && renderStep2()}
              </>
            ),
          },
          {
            key: 'plans',
            label: '方案列表',
            children: (
              <>
                <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
                  <Select
                    allowClear
                    placeholder="按状态筛选"
                    style={{ width: 160 }}
                    value={statusFilter}
                    onChange={(v) => { setPlanPage(1); setStatusFilter(v) }}
                    options={AI_PLAN_STATUS_OPTIONS}
                  />
                  <Button icon={<ReloadOutlined />} onClick={() => loadPlans()}>刷新</Button>
                </div>
                <Table
                  columns={planColumns}
                  dataSource={plans}
                  rowKey="id"
                  loading={listLoading}
                  pagination={{
                    current: planPage,
                    pageSize: 20,
                    total: planTotal,
                    onChange: setPlanPage,
                    showTotal: (t) => `共 ${t} 个计划`,
                  }}
                  locale={{ emptyText: <Empty description="暂无 AI 采集计划，去「采集向导」创建一个" /> }}
                />
              </>
            ),
          },
        ]}
      />

      {/* 试采日志抽屉（轮询模式与任务日志一致） */}
      <LogDrawer task={logTask} spiderMap={PSEUDO_SPIDER_MAP} onClose={() => setLogTask(null)} />
      {/* 试采结果抽屉 */}
      <ResultDrawer task={resultTask} spiderMap={PSEUDO_SPIDER_MAP} onClose={() => setResultTask(null)} />
    </Card>
  )
}

export default AiPlans
