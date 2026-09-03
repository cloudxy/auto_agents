/**
 * 错误信息提取（工单 72 单源：两应用共用）
 *
 * 统一替代 `catch (error: any)` / `e instanceof Error ? e.message : String(e)`
 * / `error?.response?.data?.message` 三种漂移写法：unknown 捕获 + 类型窄化，
 * 优先后端信封 message，其次原生 message，最后回退文案。
 */

interface ApiErrorLike {
  response?: { data?: { message?: string; detail?: string } }
  message?: string
}

interface FormValidateErrorLike {
  errorFields?: unknown
}

const isApiErrorLike = (e: unknown): e is ApiErrorLike =>
  typeof e === 'object' && e !== null && 'response' in e

const isFormValidateErrorLike = (e: unknown): e is FormValidateErrorLike =>
  typeof e === 'object' && e !== null && 'errorFields' in e

/** antd 表单校验失败（errorFields 存在）：提示已由表单展示，调用方静默即可 */
export const isFormValidateError = (e: unknown): boolean => isFormValidateErrorLike(e)

/** 从未知错误中提取用户可读消息：优先后端 message，其次原生 message，最后回退文案 */
export const apiErrorMessage = (e: unknown, fallback: string): string => {
  if (isApiErrorLike(e)) {
    return e.response?.data?.message || e.response?.data?.detail || e.message || fallback
  }
  if (e instanceof Error) return e.message || fallback
  return fallback
}
