/**
 * 爬虫模块服务 - 任务/注册表/日志/删除 API 封装
 *
 * 响应为后端统一信封（ADR-001）：分页端点 tasks/results 为 PaginatedResponse
 * （data.items/total），其余为 ApiResponse；service 层统一解包 data，
 * 页面组件拿到的仍是裸结构。例外：exportResults 为二进制流下载（白名单，不解包）。
 */
import api, { unwrap } from './api'

export interface SpiderParamField {
  name: string
  label: string
  kind: 'urls' | 'text' | 'json' | 'select' | string
  required?: boolean
  default?: string | null
  help?: string | null
  options?: { value: string; label: string }[] | null
}

export interface SpiderTypeInfo {
  type: string
  label: string
  fields: SpiderParamField[]
}

export interface SpiderInfo {
  name: string
  title: string
  type: string
  description?: string
}

export interface SpiderRegistry {
  types: SpiderTypeInfo[]
  spiders: SpiderInfo[]
}

export interface Task {
  id: number
  spider_name: string
  status: 'pending' | 'running' | 'completed' | 'failed' | string
  priority?: 'high' | 'normal' | 'low' | string
  result_count: number
  retry_count?: number
  error_message?: string | null
  params?: string | null
  created_at?: string | null
  started_at?: string | null
  completed_at?: string | null
}

export interface TaskLogResponse {
  task_id: number
  spider_name: string
  status: string
  lines: string[]
}

export interface SpiderResult {
  id: number
  task_id: number
  spider_name: string
  url?: string | null
  title?: string | null
  content?: string | null
  source?: string | null
  item_type?: string | null
  extra?: string | null
  content_hash?: string | null
  created_at?: string | null
}

export interface SpiderSchedule {
  id: number
  spider_name: string
  cron_expr: string
  params?: string | null
  enabled: boolean
  last_run_at?: string | null
  next_run_at?: string | null
  created_at?: string | null
}

export interface TaskStoreStatus {
  task_id: number
  targets: string[]
  redis_count?: number | null
  csv_path?: string | null
}

export interface SpiderFile {
  name: string
  file: string
  size_bytes: number
  registered: boolean
  enabled?: boolean | null
  title?: string | null
}

/** 爬虫注册表（新增任务弹窗的数据源；后端 SPIDER_TYPES 未登记 flow 类型时前端兖底补齐） */
export const fetchRegistry = (): Promise<SpiderRegistry> =>
  api
    .get('/spiders/registry')
    .then((res) => unwrap<SpiderRegistry>(res))
    .then((reg) => {
      if (reg.types && !reg.types.some((t) => t.type === 'flow')) {
        reg.types = [...reg.types, FLOW_TYPE_FALLBACK]
      }
      return reg
    })

/** flow 类型表单定义（与 plan_json 的 flow 契约对齐：selectors/pagination/detail/filters） */
export const FLOW_TYPE_FALLBACK: SpiderTypeInfo = {
  type: 'flow',
  label: '流程化采集',
  fields: [
    { name: 'urls', label: '页面地址', kind: 'urls', required: true, help: '待采集的列表页 URL，可填多个（每行一个）' },
    { name: 'selectors', label: '提取规则', kind: 'selectors', required: true, help: '字段名 + 选择器类型（xpath/css/regex）+ 表达式，可增删多行' },
    { name: 'pagination', label: '分页设置', kind: 'pagination', help: '可选：下一页选择器 + 最大页数，自动翻页' },
    { name: 'detail', label: '详情页设置', kind: 'detail', help: '可选：列表项选择器 + 链接选择器 + 详情页字段规则，二次采集详情页' },
    { name: 'filters', label: '条件过滤', kind: 'filters', help: '可选：按 包含/等于/正则 过滤提取字段值（字段/操作符/值）' },
  ],
}

/** 任务列表（分页信封 data：{items, total, page, page_size, total_pages}，可选优先级筛选） */
export const fetchTasks = (
  skip = 0,
  limit = 20,
  filters?: { priority?: string; status?: string; spider_name?: string }
): Promise<{ total: number; items: Task[] }> =>
  api
    .get('/spiders/tasks', {
      params: { skip, limit, ...filters },
    })
    .then((res) => unwrap<{ total: number; items: Task[] }>(res))

/** 提交新任务（params 为 JSON 字符串，priority 可选：high/normal/low，默认 normal） */
export const runSpider = (
  spider_name: string,
  params: string,
  priority: 'high' | 'normal' | 'low' = 'normal'
): Promise<Task> =>
  api
    .post('/spiders/run', { spider_name, params, priority })
    .then((res) => unwrap<Task>(res))

/** 删除任务（级联删除采集结果） */
export const deleteTask = (taskId: number): Promise<{ task_id: number; removed_results: number }> =>
  api
    .delete(`/spiders/tasks/${taskId}`)
    .then((res) => unwrap<{ task_id: number; removed_results: number }>(res))

/** 控制运行中的任务：暂停/恢复/终止（A4） */
export const controlTask = (
  taskId: number,
  action: 'pause' | 'resume' | 'stop'
): Promise<{ task_id: number; action: string; message: string }> =>
  api
    .post(`/spiders/tasks/${taskId}/control`, { action })
    .then((res) => unwrap<{ task_id: number; action: string; message: string }>(res))

/** 任务运行日志（尾部 N 行，支持关键词搜索和级别过滤） */
export const fetchTaskLogs = (
  taskId: number,
  lines = 200,
  keyword?: string,
  level?: string,
): Promise<TaskLogResponse> => {
  const params: Record<string, unknown> = { lines }
  if (keyword) params.keyword = keyword
  if (level) params.level = level
  return api
    .get(`/spiders/tasks/${taskId}/logs`, { params })
    .then((res) => unwrap<TaskLogResponse>(res))
}

/** 任务采集结果（分页信封 data） */
export const fetchResults = (
  taskId: number,
  skip = 0,
  limit = 50
): Promise<{ total: number; items: SpiderResult[] }> =>
  api
    .get(`/spiders/results/${taskId}`, { params: { skip, limit } })
    .then((res) => unwrap<{ total: number; items: SpiderResult[] }>(res))

/** 任务额外存储目标状态（4.2：目标清单 / redis 缓存条数 / csv 落盘路径） */
export const fetchTaskStore = (taskId: number): Promise<TaskStoreStatus> =>
  api.get(`/spiders/tasks/${taskId}/store`).then((res) => unwrap<TaskStoreStatus>(res))

/** 代码爬虫文件清单（4.4：只读元数据 + 启停状态；data={total, items}） */
export const fetchSpiderFiles = (): Promise<{ total: number; items: SpiderFile[] }> =>
  api.get('/spiders/files').then((res) => unwrap<{ total: number; items: SpiderFile[] }>(res))

/** 启停代码爬虫（4.4：写 spider_definitions.enabled，后端仅 admin） */
export const updateDefinition = (name: string, enabled: boolean): Promise<SpiderFile> =>
  api.patch(`/spiders/definitions/${name}`, { enabled }).then((res) => unwrap<SpiderFile>(res))

/** 结果导出（blob 下载，自动携带鉴权 Token；二进制流白名单，不解信封） */
export const exportResults = async (taskId: number, format: 'csv' | 'json'): Promise<Blob> => {
  const res = await api.get(`/spiders/results/${taskId}/export`, {
    params: { format },
    responseType: 'blob',
  })
  return res as unknown as Blob
}

// ---------------- 待执行任务编辑（阶段一）----------------
/** 编辑待执行任务（仅 pending/queued 可改 params/priority；改优先级会同步搬迁队列） */
export const updateTask = (
  taskId: number,
  payload: { params?: string; priority?: 'high' | 'normal' | 'low' }
): Promise<Task> =>
  api.patch(`/spiders/tasks/${taskId}`, payload).then((res) => unwrap<Task>(res))

// ---------------- 跨任务结果检索（数据中心）----------------
export interface SearchResultQuery {
  spider_name?: string
  keyword?: string
  start_time?: string
  end_time?: string
  page?: number
  page_size?: number
}

/** 跨任务分页查询采集结果（数据中心：爬虫/时间范围/关键词过滤） */
export const searchResults = (
  query: SearchResultQuery = {}
): Promise<{ total: number; items: SpiderResult[] }> => {
  const params: Record<string, unknown> = {
    page: query.page || 1,
    page_size: query.page_size || 20,
  }
  if (query.spider_name) params.spider_name = query.spider_name
  if (query.keyword) params.keyword = query.keyword
  if (query.start_time) params.start_time = query.start_time
  if (query.end_time) params.end_time = query.end_time
  return api
    .get('/spiders/results', { params })
    .then((res) => unwrap<{ total: number; items: SpiderResult[] }>(res))
}

/** 删除单条采集结果（数据中心清理；仅管理员） */
export const deleteResult = (
  resultId: number
): Promise<{ result_id: number; deleted: boolean }> =>
  api
    .delete(`/spiders/results/${resultId}`)
    .then((res) => unwrap<{ result_id: number; deleted: boolean }>(res))

// ---------------- 爬虫定义完整 CRUD（阶段一）----------------
export interface SpiderDefinition {
  id: number
  name: string
  title: string
  type: string
  description?: string | null
  enabled: boolean
  source?: string
}

/** 新建爬虫定义（手动登记，来源标记 manual；仅管理员；type：api/web/custom/flow） */
export const createDefinition = (payload: {
  name: string
  title: string
  type: string
  description?: string
}): Promise<SpiderDefinition> =>
  api.post('/spiders/definitions', payload).then((res) => unwrap<SpiderDefinition>(res))

/** 编辑爬虫定义元信息（标题/描述；仅管理员） */
export const updateDefinitionMeta = (
  name: string,
  payload: { title?: string; description?: string }
): Promise<SpiderDefinition> =>
  api
    .patch(`/spiders/definitions/${name}/meta`, payload)
    .then((res) => unwrap<SpiderDefinition>(res))

/** 删除爬虫定义（存在历史任务引用时后端拒绝；仅管理员） */
export const deleteDefinition = (
  name: string
): Promise<{ name: string; deleted: boolean }> =>
  api
    .delete(`/spiders/definitions/${name}`)
    .then((res) => unwrap<{ name: string; deleted: boolean }>(res))

// ---------------- 定时调度 ----------------
/** 调度计划列表（data={total, items}，非分页） */
export const fetchSchedules = (): Promise<{ total: number; items: SpiderSchedule[] }> =>
  api.get('/spiders/schedules').then((res) => unwrap<{ total: number; items: SpiderSchedule[] }>(res))

/** 创建调度计划 */
export const createSchedule = (payload: {
  spider_name: string
  cron_expr: string
  params?: string | null
  enabled?: boolean
}): Promise<SpiderSchedule> =>
  api.post('/spiders/schedules', payload).then((res) => unwrap<SpiderSchedule>(res))

/** 更新调度计划（启停/改表达式） */
export const updateSchedule = (
  scheduleId: number,
  payload: { cron_expr?: string; params?: string | null; enabled?: boolean }
): Promise<SpiderSchedule> =>
  api
    .patch(`/spiders/schedules/${scheduleId}`, payload)
    .then((res) => unwrap<SpiderSchedule>(res))

/** 删除调度计划 */
export const deleteSchedule = (
  scheduleId: number
): Promise<{ schedule_id: number; spider_name: string }> =>
  api
    .delete(`/spiders/schedules/${scheduleId}`)
    .then((res) => unwrap<{ schedule_id: number; spider_name: string }>(res))

// ---------------- 告警规则 ----------------
export interface AlertRule {
  id: number
  name: string
  spider_name?: string | null
  rule_type: string
  threshold: number
  window_minutes: number
  severity: string
  channels?: string[] | null
  enabled: boolean
  last_triggered_at?: string | null
  created_at?: string | null
}

/** 告警规则列表（data=[...]） */
export const fetchAlertRules = (): Promise<AlertRule[]> =>
  api.get('/spiders/alert-rules').then((res) => unwrap<AlertRule[]>(res))

/** 创建告警规则 */
export const createAlertRule = (payload: {
  name: string
  spider_name?: string | null
  rule_type: string
  threshold: number
  window_minutes?: number
  severity?: string
  channels?: string[] | null
  enabled?: boolean
}): Promise<AlertRule> =>
  api.post('/spiders/alert-rules', payload).then((res) => unwrap<AlertRule>(res))

/** 更新告警规则 */
export const updateAlertRule = (
  ruleId: number,
  payload: {
    name?: string
    threshold?: number
    window_minutes?: number
    severity?: string
    channels?: string[] | null
    enabled?: boolean
  }
): Promise<AlertRule> =>
  api.patch(`/spiders/alert-rules/${ruleId}`, payload).then((res) => unwrap<AlertRule>(res))

/** 删除告警规则 */
export const deleteAlertRule = (ruleId: number): Promise<{ rule_id: number; deleted: boolean }> =>
  api
    .delete(`/spiders/alert-rules/${ruleId}`)
    .then((res) => unwrap<{ rule_id: number; deleted: boolean }>(res))

// ---------------- 任务模板（C1）----------------
export interface TaskTemplate {
  id: number
  name: string
  spider_name: string
  params?: string | null
  priority: string
  created_by?: number | null
  created_at?: string | null
}

/** 模板列表（data=[...]） */
export const fetchTemplates = (): Promise<TaskTemplate[]> =>
  api.get('/spiders/templates').then((res) => unwrap<TaskTemplate[]>(res))

/** 创建模板 */
export const createTemplate = (payload: {
  name: string
  spider_name: string
  params?: string | null
  priority?: string
}): Promise<TaskTemplate> =>
  api.post('/spiders/templates', payload).then((res) => unwrap<TaskTemplate>(res))

/** 更新模板 */
export const updateTemplate = (
  templateId: number,
  payload: {
    name?: string
    spider_name?: string
    params?: string | null
    priority?: string
  }
): Promise<TaskTemplate> =>
  api
    .patch(`/spiders/templates/${templateId}`, payload)
    .then((res) => unwrap<TaskTemplate>(res))

/** 删除模板 */
export const deleteTemplate = (templateId: number): Promise<{ id: number; deleted: boolean }> =>
  api
    .delete(`/spiders/templates/${templateId}`)
    .then((res) => unwrap<{ id: number; deleted: boolean }>(res))

/** 从模板创建并运行任务 */
export const runFromTemplate = (templateId: number): Promise<Task> =>
  api.post(`/spiders/templates/${templateId}/run`).then((res) => unwrap<Task>(res))
