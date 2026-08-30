/**
 * 爬虫模块服务 - 任务/注册表/日志/删除 API 封装
 */
import api from './api'

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

/** 爬虫注册表（新增任务弹窗的数据源；后端 SPIDER_TYPES 未登记 flow 类型时前端兜底补齐） */
export const fetchRegistry = (): Promise<SpiderRegistry> => {
  return (api.get('/spiders/registry') as unknown as Promise<SpiderRegistry>).then((reg) => {
    if (reg.types && !reg.types.some((t) => t.type === 'flow')) {
      reg.types = [...reg.types, FLOW_TYPE_FALLBACK]
    }
    return reg
  })
}

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

/** 任务列表（分页，可选优先级筛选） */
export const fetchTasks = (
  skip = 0,
  limit = 20,
  priority?: string
): Promise<{ total: number; items: Task[] }> => {
  return api.get('/spiders/tasks', {
    params: { skip, limit, ...(priority ? { priority } : {}) },
  }) as unknown as Promise<{
    total: number
    items: Task[]
  }>
}

/** 提交新任务（params 为 JSON 字符串，priority 可选：high/normal/low，默认 normal） */
export const runSpider = (
  spider_name: string,
  params: string,
  priority: 'high' | 'normal' | 'low' = 'normal'
): Promise<Task> => {
  return api.post('/spiders/run', { spider_name, params, priority }) as unknown as Promise<Task>
}

/** 删除任务（级联删除采集结果） */
export const deleteTask = (taskId: number): Promise<{ task_id: number; removed_results: number }> => {
  return api.delete(`/spiders/tasks/${taskId}`) as unknown as Promise<{
    task_id: number
    removed_results: number
  }>
}

/** 控制运行中的任务：暂停/恢复/终止（A4） */
export const controlTask = (
  taskId: number,
  action: 'pause' | 'resume' | 'stop'
): Promise<{ task_id: number; action: string; message: string }> => {
  return api.post(`/spiders/tasks/${taskId}/control`, { action }) as unknown as Promise<{
    task_id: number
    action: string
    message: string
  }>
}

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
  return api.get(`/spiders/tasks/${taskId}/logs`, { params }) as unknown as Promise<TaskLogResponse>
}

/** 任务采集结果（分页） */
export const fetchResults = (
  taskId: number,
  skip = 0,
  limit = 50
): Promise<{ total: number; items: SpiderResult[] }> => {
  return api.get(`/spiders/results/${taskId}`, { params: { skip, limit } }) as unknown as Promise<{
    total: number
    items: SpiderResult[]
  }>
}

/** 任务额外存储目标状态（4.2：目标清单 / redis 缓存条数 / csv 落盘路径） */
export const fetchTaskStore = (taskId: number): Promise<TaskStoreStatus> => {
  return api.get(`/spiders/tasks/${taskId}/store`) as unknown as Promise<TaskStoreStatus>
}

/** 代码爬虫文件清单（4.4：只读元数据 + 启停状态） */
export const fetchSpiderFiles = (): Promise<{ total: number; items: SpiderFile[] }> => {
  return api.get('/spiders/files') as unknown as Promise<{ total: number; items: SpiderFile[] }>
}

/** 启停代码爬虫（4.4：写 spider_definitions.enabled，后端仅 admin） */
export const updateDefinition = (name: string, enabled: boolean): Promise<SpiderFile> => {
  return api.patch(`/spiders/definitions/${name}`, { enabled }) as unknown as Promise<SpiderFile>
}

/** 结果导出（blob 下载，自动携带鉴权 Token） */
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
): Promise<Task> => {
  return api.patch(`/spiders/tasks/${taskId}`, payload) as unknown as Promise<Task>
}

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
  return api.get('/spiders/results', { params }) as unknown as Promise<{
    total: number
    items: SpiderResult[]
  }>
}

/** 删除单条采集结果（数据中心清理；仅管理员） */
export const deleteResult = (
  resultId: number
): Promise<{ result_id: number; deleted: boolean }> => {
  return api.delete(`/spiders/results/${resultId}`) as unknown as Promise<{
    result_id: number
    deleted: boolean
  }>
}

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
}): Promise<SpiderDefinition> => {
  return api.post('/spiders/definitions', payload) as unknown as Promise<SpiderDefinition>
}

/** 编辑爬虫定义元信息（标题/描述；仅管理员） */
export const updateDefinitionMeta = (
  name: string,
  payload: { title?: string; description?: string }
): Promise<SpiderDefinition> => {
  return api.patch(`/spiders/definitions/${name}/meta`, payload) as unknown as Promise<SpiderDefinition>
}

/** 删除爬虫定义（存在历史任务引用时后端拒绝；仅管理员） */
export const deleteDefinition = (
  name: string
): Promise<{ name: string; deleted: boolean }> => {
  return api.delete(`/spiders/definitions/${name}`) as unknown as Promise<{
    name: string
    deleted: boolean
  }>
}

// ---------------- 定时调度 ----------------
/** 调度计划列表 */
export const fetchSchedules = (): Promise<{ total: number; items: SpiderSchedule[] }> => {
  return api.get('/spiders/schedules') as unknown as Promise<{ total: number; items: SpiderSchedule[] }>
}

/** 创建调度计划 */
export const createSchedule = (payload: {
  spider_name: string
  cron_expr: string
  params?: string | null
  enabled?: boolean
}): Promise<SpiderSchedule> => {
  return api.post('/spiders/schedules', payload) as unknown as Promise<SpiderSchedule>
}

/** 更新调度计划（启停/改表达式） */
export const updateSchedule = (
  scheduleId: number,
  payload: { cron_expr?: string; params?: string | null; enabled?: boolean }
): Promise<SpiderSchedule> => {
  return api.patch(`/spiders/schedules/${scheduleId}`, payload) as unknown as Promise<SpiderSchedule>
}

/** 删除调度计划 */
export const deleteSchedule = (
  scheduleId: number
): Promise<{ schedule_id: number; spider_name: string }> => {
  return api.delete(`/spiders/schedules/${scheduleId}`) as unknown as Promise<{
    schedule_id: number
    spider_name: string
  }>
}

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

/** 告警规则列表 */
export const fetchAlertRules = (): Promise<AlertRule[]> => {
  return api.get('/spiders/alert-rules') as unknown as Promise<AlertRule[]>
}

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
}): Promise<AlertRule> => {
  return api.post('/spiders/alert-rules', payload) as unknown as Promise<AlertRule>
}

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
): Promise<AlertRule> => {
  return api.patch(`/spiders/alert-rules/${ruleId}`, payload) as unknown as Promise<AlertRule>
}

/** 删除告警规则 */
export const deleteAlertRule = (ruleId: number): Promise<{ rule_id: number; deleted: boolean }> => {
  return api.delete(`/spiders/alert-rules/${ruleId}`) as unknown as Promise<{
    rule_id: number
    deleted: boolean
  }>
}

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

/** 模板列表 */
export const fetchTemplates = (): Promise<TaskTemplate[]> => {
  return api.get('/spiders/templates') as unknown as Promise<TaskTemplate[]>
}

/** 创建模板 */
export const createTemplate = (payload: {
  name: string
  spider_name: string
  params?: string | null
  priority?: string
}): Promise<TaskTemplate> => {
  return api.post('/spiders/templates', payload) as unknown as Promise<TaskTemplate>
}

/** 更新模板 */
export const updateTemplate = (
  templateId: number,
  payload: {
    name?: string
    spider_name?: string
    params?: string | null
    priority?: string
  }
): Promise<TaskTemplate> => {
  return api.patch(`/spiders/templates/${templateId}`, payload) as unknown as Promise<TaskTemplate>
}

/** 删除模板 */
export const deleteTemplate = (templateId: number): Promise<{ id: number; deleted: boolean }> => {
  return api.delete(`/spiders/templates/${templateId}`) as unknown as Promise<{
    id: number
    deleted: boolean
  }>
}

/** 从模板创建并运行任务 */
export const runFromTemplate = (templateId: number): Promise<Task> => {
  return api.post(`/spiders/templates/${templateId}/run`) as unknown as Promise<Task>
}
