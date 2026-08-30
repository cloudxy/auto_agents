/**
 * AI 采集计划服务 - /ai 端点封装（阶段二）
 *
 * 响应为后端 Pydantic 直出（无 ApiResponse 信封），与 services/spiders.ts 解包方式一致。
 * 状态机：draft → planning →（draft，含 flow 产物）→ testing →（试采通过保持 testing，可注册）→ registered；任意阶段可 failed。
 */
import api from './api'

/** 字段提取规则（selector_engine 消费格式） */
export interface FlowSelector {
  name: string
  type: 'xpath' | 'css' | 'regex' | string
  expr: string
}

/** 翻页配置（下一页链接仅支持 css/xpath） */
export interface FlowPagination {
  selector: string
  type: 'css' | 'xpath' | string
  max_pages: number
}

/** 详情页二次采集配置（list_selector 走 css，url_selector 必须是 xpath） */
export interface FlowDetail {
  list_selector: string
  url_selector: string
  selectors: FlowSelector[]
}

/** 条件过滤规则 */
export interface FlowFilter {
  field: string
  op: 'contains' | 'equals' | 'regex' | string
  value: string
}

/** flow_generic 流程定义契约（plan_json.flow 结构） */
export interface FlowConfig {
  selectors: FlowSelector[]
  pagination?: FlowPagination | null
  detail?: FlowDetail | null
  filters?: FlowFilter[]
  render_js?: boolean
  wait_for?: string | null
  wait_timeout?: number | null
}

/** 试采历史条目（plan_json.test_history） */
export interface AiPlanTestHistory {
  iteration: number
  task_id: number
  status: string
  result_count: number
  passed: boolean
  reason: string
}

/** AI 采集计划快照 */
export interface AiPlan {
  id: number
  target_url: string
  status: 'draft' | 'planning' | 'testing' | 'registered' | 'failed' | string
  plan_json?: {
    flow?: FlowConfig | null
    test_history?: AiPlanTestHistory[]
    html_sample?: string
    html_snippet?: string
    registered_definition?: string
  } | null
  generated_params?: Record<string, unknown> | null
  test_task_id?: number | null
  iteration_count?: number
  error_message?: string | null
  created_by?: string | null
  created_at?: string | null
  updated_at?: string | null
}

/** 计划状态中文标签与颜色（列表/向导共用） */
export const AI_PLAN_STATUS_META: Record<string, { label: string; color: string }> = {
  draft: { label: '草稿', color: 'default' },
  planning: { label: '规划中', color: 'processing' },
  testing: { label: '试采中', color: 'orange' },
  registered: { label: '已上线', color: 'success' },
  failed: { label: '失败', color: 'error' },
}

/** 计划状态筛选项 */
export const AI_PLAN_STATUS_OPTIONS = [
  { value: 'draft', label: '草稿' },
  { value: 'planning', label: '规划中' },
  { value: 'testing', label: '试采中' },
  { value: 'registered', label: '已上线' },
  { value: 'failed', label: '失败' },
]

/** 是否处于需要轮询的进行中状态（planning 恒轮询；testing 最后一轮未通过时仍在自动修复迭代） */
export const isPlanPolling = (plan: AiPlan | null): boolean => {
  if (!plan) return false
  if (plan.status === 'planning') return true
  if (plan.status === 'testing') {
    const history = plan.plan_json?.test_history || []
    return !(history.length > 0 && history[history.length - 1].passed)
  }
  return false
}

/** 最近一次试采是否通过（注册按钮的可用条件，与后端 register 校验一致） */
export const isLatestTestPassed = (plan: AiPlan | null): boolean => {
  const history = plan?.plan_json?.test_history || []
  return history.length > 0 && !!history[history.length - 1].passed
}

/** 创建 AI 采集计划（draft；html_snippet 可选，预置后跳过在线抓取） */
export const createAiPlan = (payload: {
  target_url: string
  html_snippet?: string
}): Promise<AiPlan> => {
  return api.post('/ai/plans', payload) as unknown as Promise<AiPlan>
}

/** 计划分页列表（可按状态过滤） */
export const fetchAiPlans = (params: {
  skip?: number
  limit?: number
  status?: string
} = {}): Promise<{ total: number; items: AiPlan[] }> => {
  return api.get('/ai/plans', { params }) as unknown as Promise<{
    total: number
    items: AiPlan[]
  }>
}

/** 计划快照（状态机进度查询，轮询用） */
export const fetchAiPlan = (planId: number): Promise<AiPlan> => {
  return api.get(`/ai/plans/${planId}`) as unknown as Promise<AiPlan>
}

/** 触发 LLM 规划（后台执行，立即返回 planning 快照） */
export const triggerAiPlan = (planId: number): Promise<AiPlan> => {
  return api.post(`/ai/plans/${planId}/plan`) as unknown as Promise<AiPlan>
}

/** 触发 flow_generic 试采（后台执行含自动修复迭代，立即返回快照） */
export const triggerAiTest = (planId: number): Promise<AiPlan> => {
  return api.post(`/ai/plans/${planId}/test`) as unknown as Promise<AiPlan>
}

/** 注册为爬虫定义（校验最近试采通过；source=ai_generated，type=flow） */
export const registerAiPlan = (planId: number): Promise<AiPlan> => {
  return api.post(`/ai/plans/${planId}/register`) as unknown as Promise<AiPlan>
}

/** 删除 AI 采集计划（仅管理员；规划/试采进行中后端拒绝） */
export const deleteAiPlan = (planId: number): Promise<{ id: number; deleted: boolean }> => {
  return api.delete(`/ai/plans/${planId}`) as unknown as Promise<{ id: number; deleted: boolean }>
}
