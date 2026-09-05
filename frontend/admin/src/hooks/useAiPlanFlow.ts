/**
 * AI 采集向导状态机 hook（从 pages/AiPlans.tsx 拆出，期 4 前端治理）
 *
 * 职责：三步向导的全部状态（step/plan/editedFlow/customTask）+ 轮询副作用
 * （计划状态 2.5s、调整方案试采任务 3s）+ 动作函数（创建/规划/试采/上线）。
 * 页面组件只负责组合（Tabs/抽屉/权限），不再持有向导内部状态。
 *
 * 轮询模式沿用全局约定：2.5s 间隔，仅 planning/testing（未通过）状态轮询。
 */
import { useCallback, useEffect, useState } from 'react'
import { Form, message } from 'antd'
import type { FormInstance } from 'antd'
import {
  isPlanPolling, isLatestTestPassed,
  createAiPlan, fetchAiPlan, triggerAiPlan, triggerAiTest, registerAiPlan,
} from '../services/ai'
import type { AiPlan, AiPlanTestHistory, FlowConfig } from '../services/ai'
import { fetchTaskLogs, runSpider } from '../services/spiders'
import type { Task } from '../components/spider/types'
import { apiErrorMessage, isFormValidateError } from '../utils/errorMessage'
import { useQuery } from '@tanstack/react-query'

/** 表单草稿行（antd validateFields 返回 any，显式窄化以通过 noImplicitAny） */
interface SelectorRowDraft { name?: unknown; type?: string; expr?: unknown }
interface PaginationDraft { selector?: unknown; type?: string; max_pages?: unknown }
interface DetailDraft { list_selector?: unknown; url_selector?: unknown }
interface FilterRowDraft { field?: unknown; op?: string; value?: unknown }

export interface AiPlanFlow {
  /** 当前向导步骤（0 创建 / 1 方案预览 / 2 试采上线） */
  step: number
  plan: AiPlan | null
  flow: FlowConfig | null
  history: AiPlanTestHistory[]
  latestPassed: boolean
  creating: boolean
  /** 进行中动作标记（'plan' | 'test' | 'test_edited' | 'register'，空串表示空闲） */
  actionLoading: string
  editedFlow: FlowConfig | null
  /** 调整方案直跑的试采任务 */
  customTask: Task | null
  createForm: FormInstance
  flowForm: FormInstance
  setStep: (step: number) => void
  onCreate: () => Promise<void>
  onReplan: () => Promise<void>
  onTest: () => Promise<void>
  onTestEdited: () => Promise<void>
  onApplyFlowEdit: () => Promise<void>
  onRegister: () => Promise<void>
  resetWizard: () => void
  /** 从列表载入计划到向导（tab 切换由页面组合层负责） */
  openPlanInWizard: (p: AiPlan) => void
  /** 带最近试采结果条数打开结果抽屉的载荷构造 */
  resultsTaskOf: (p: AiPlan) => Task
}

export const useAiPlanFlow = (): AiPlanFlow => {
  // 向导状态
  const [step, setStep] = useState(0)
  const [plan, setPlan] = useState<AiPlan | null>(null)
  const [creating, setCreating] = useState(false)
  const [actionLoading, setActionLoading] = useState('')
  const [editedFlow, setEditedFlow] = useState<FlowConfig | null>(null)
  const [customTask, setCustomTask] = useState<Task | null>(null)
  const [createForm] = Form.useForm()
  const [flowForm] = Form.useForm()

  const flow = plan?.plan_json?.flow || null
  const history: AiPlanTestHistory[] = plan?.plan_json?.test_history || []
  const latestPassed = isLatestTestPassed(plan)

  // ---------------- 计划状态轮询（工单 78：react-query 托管，2.5s，仅进行中）----------------
  const { data: freshPlan } = useQuery({
    queryKey: ['ai-plan-poll', plan?.id],
    queryFn: () => fetchAiPlan(plan!.id),
    enabled: !!plan && isPlanPolling(plan),
    refetchInterval: 2500,
  })
  useEffect(() => {
    if (!freshPlan) return
    setPlan(freshPlan)
    if (freshPlan.status === 'testing' || freshPlan.status === 'registered') {
      setStep((s) => (s < 2 ? 2 : s))
    }
  }, [freshPlan])

  // ---------------- 调整方案试采任务状态轮询（react-query 托管，3s，仅进行中）----------------
  const pollingTaskId = customTask && (customTask.status === 'pending' || customTask.status === 'running') ? customTask.id : 0
  const { data: polledTaskStatus } = useQuery({
    queryKey: ['ai-plan-task-poll', pollingTaskId],
    queryFn: () => fetchTaskLogs(pollingTaskId, 5),
    enabled: pollingTaskId > 0,
    refetchInterval: (query) => {
      const s = query.state.data?.status
      return s === 'pending' || s === 'running' ? 3000 : false
    },
  })
  useEffect(() => {
    if (!polledTaskStatus) return
    setCustomTask((prev) => (prev && prev.id === pollingTaskId ? { ...prev, status: polledTaskStatus.status } : prev))
  }, [polledTaskStatus, pollingTaskId])

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
    } catch (error) {
      if (isFormValidateError(error)) return
      message.error(apiErrorMessage(error, '创建计划失败'))
    } finally {
      setCreating(false)
    }
  }

  const resetWizard = useCallback(() => {
    setPlan(null)
    setStep(0)
    setEditedFlow(null)
    setCustomTask(null)
    createForm.resetFields()
    flowForm.resetFields()
  }, [createForm, flowForm])

  const onReplan = async () => {
    if (!plan) return
    try {
      setActionLoading('plan')
      const snapshot = await triggerAiPlan(plan.id)
      setPlan(snapshot)
      setEditedFlow(null)
      setStep(1)
      message.success('已重新触发规划')
    } catch (error) {
      message.error(apiErrorMessage(error, '触发规划失败'))
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
    } catch (error) {
      message.error(apiErrorMessage(error, '触发试采失败'))
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
    } catch (error) {
      message.error(apiErrorMessage(error, '提交试采失败'))
    } finally {
      setActionLoading('')
    }
  }

  const onApplyFlowEdit = async () => {
    try {
      const values = await flowForm.validateFields()
      const rows = (Array.isArray(values.selectors) ? values.selectors : []) as SelectorRowDraft[]
      const selectors = rows
        .filter((r) => r && String(r.name || '').trim() && String(r.expr || '').trim())
        .map((r) => ({ name: String(r.name).trim(), type: r.type || 'css', expr: String(r.expr).trim() }))
      if (!selectors.length) {
        message.error('请至少保留一条提取规则')
        return
      }
      const p = (values.pagination || {}) as PaginationDraft
      const pagination = String(p.selector || '').trim()
        ? { selector: String(p.selector).trim(), type: p.type || 'css', max_pages: Number(p.max_pages) || 2 }
        : null
      const d = (values.detail || {}) as DetailDraft
      const detailRows = (Array.isArray(values.detail_selectors) ? values.detail_selectors : []) as SelectorRowDraft[]
      const detailSelectors = detailRows
        .filter((r) => r && String(r.name || '').trim() && String(r.expr || '').trim())
        .map((r) => ({ name: String(r.name).trim(), type: r.type || 'css', expr: String(r.expr).trim() }))
      const detail = String(d.list_selector || '').trim() && String(d.url_selector || '').trim()
        ? {
            list_selector: String(d.list_selector).trim(),
            url_selector: String(d.url_selector).trim(),
            selectors: detailSelectors,
          }
        : null
      const filterRows = (Array.isArray(values.filters) ? values.filters : []) as FilterRowDraft[]
      const filters = filterRows
        .filter((r) => r && String(r.field || '').trim() && String(r.value || '').trim())
        .map((r) => ({ field: String(r.field).trim(), op: r.op || 'contains', value: String(r.value).trim() }))
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
    } catch (error) {
      if (isFormValidateError(error)) return // 表单校验失败
      message.error(apiErrorMessage(error, '应用调整失败'))
    }
  }

  const onRegister = async () => {
    if (!plan) return
    try {
      setActionLoading('register')
      const snapshot = await registerAiPlan(plan.id)
      setPlan(snapshot)
      message.success(`已上线为爬虫定义：${snapshot.plan_json?.registered_definition || '-'}（类型 flow）`)
    } catch (error) {
      message.error(apiErrorMessage(error, '上线失败'))
    } finally {
      setActionLoading('')
    }
  }

  // 从列表载入计划到向导（依据状态机进度定位步骤）
  const openPlanInWizard = useCallback((p: AiPlan) => {
    setPlan(p)
    setEditedFlow(null)
    setCustomTask(null)
    const hist = p.plan_json?.test_history || []
    if (p.status === 'testing' || p.status === 'registered' || (p.status === 'failed' && hist.length > 0)) {
      setStep(2)
    } else {
      setStep(1)
    }
  }, [])

  // 带最近试采结果条数构造结果抽屉载荷
  const resultsTaskOf = useCallback((p: AiPlan): Task => {
    const last = (p.plan_json?.test_history || []).slice(-1)[0]
    const status = p.status === 'registered' ? 'completed' : 'running'
    return { id: p.test_task_id!, spider_name: 'flow_generic', status, priority: 'low', result_count: last?.result_count || 0 }
  }, [])

  return {
    step, plan, flow, history, latestPassed, creating, actionLoading, editedFlow, customTask,
    createForm, flowForm, setStep,
    onCreate, onReplan, onTest, onTestEdited, onApplyFlowEdit, onRegister,
    resetWizard, openPlanInWizard, resultsTaskOf,
  }
}
