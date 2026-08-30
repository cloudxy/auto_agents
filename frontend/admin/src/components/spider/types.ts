/**
 * 爬虫管理模块 - 共享类型与常量
 */
import type {
  Task, SpiderRegistry, SpiderSchedule, SpiderFile,
  AlertRule, TaskTemplate, SpiderResult, TaskStoreStatus,
  TaskLogResponse, SpiderParamField,
} from '../../services/spiders'

// Re-export for convenience
export type {
  Task, SpiderRegistry, SpiderSchedule, SpiderFile,
  AlertRule, TaskTemplate, SpiderResult, TaskStoreStatus,
  TaskLogResponse, SpiderParamField,
}

export const STATUS_META: Record<string, { label: string; color: string }> = {
  pending: { label: '待执行', color: 'gold' },
  running: { label: '运行中', color: 'processing' },
  completed: { label: '已完成', color: 'green' },
  failed: { label: '失败', color: 'red' },
}

export const PRIORITY_META: Record<string, { label: string; color: string }> = {
  high: { label: '高', color: 'red' },
  normal: { label: '普通', color: 'blue' },
  low: { label: '低', color: 'default' },
}

/** SpiderMap：名称 → {title, type} 的映射 */
export type SpiderMap = Record<string, { title: string; type: string }>
