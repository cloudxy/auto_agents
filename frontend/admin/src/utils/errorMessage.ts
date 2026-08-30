/**
 * 错误信息提取工具（any 消减配套）
 *
 * 统一替代页面组件中 `catch (error: any)` + `error?.response?.data?.message` 的
 * 无类型访问模式：catch 子句用 unknown 捕获，经类型窄化提取后端 message。
 */

interface ApiErrorLike {
  /** FastAPI 统一信封错误字段（message）与 422 校验错误字段（detail） */
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
