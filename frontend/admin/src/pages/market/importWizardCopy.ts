/** T-36 一键导入向导冻结句（edge-states「一键导入向导」屏；FR-100 / ADR-0023）。
 * 逐条失败原因由 T-35 后端成品中文句直出，前端不造第二套句式。 */

export const IMPORT_ENTRY = '导入资产'
export const IMPORT_STEP_SELECT = '选择来源'
export const IMPORT_STEP_RESULT = '导入结果'
export const IMPORT_CHOOSE_HINT = '选择包含 skill、agent、command 或 plugin 的文件或目录压缩包。类型由导入过程自动判定。'
export const IMPORT_SELECT = '选择文件 / 目录'
export const IMPORT_DIR_LABEL = '目录路径'
export const IMPORT_DIR_PLACEHOLDER = '服务器上的资产目录路径'
export const IMPORT_EXCLUSIVE = '文件与目录只能二选一'
export const IMPORT_START = '开始导入'
export const IMPORTING = '导入中…'
export const IMPORT_PARSING = '解析中…'
export const IMPORT_NETWORK_FAIL = '导入没有开始：网络不可用。'
export const IMPORT_PARSE_RETRY = '检查文件格式后重试'
export const IMPORT_EMPTY_BATCH = '没有可导入的资产。'
export const IMPORT_RESELECT = '重新选择'
export const IMPORT_FINISH = '完成'
export const IMPORT_CANCEL = '取消'
export const IMPORT_RETRY = '重试'
export const IMPORT_STATUS_OK = '已导入'
export const IMPORT_STATUS_FAIL = '未导入'
export const IMPORT_STATUS_SKIP = '已存在，跳过'
export const IMPORT_UNLISTED_NOTE = '已导入，未上架。上架请在治理目录操作。'

/** 四类中文化（GWT-100.4：类型由导入过程判定，无需手工分型） */
export const IMPORT_TYPE_LABELS: Record<string, string> = {
  skill: '技能',
  command: '命令',
  agent: '智能体',
  plugin: '插件',
}

export const uploadingCopy = (percent: number): string => `上传中…${percent}%`

/** 汇总行（packet 钉句）：成功 N · 失败 N · 跳过 N */
export const summaryCopy = (succeeded: number, failed: number, skipped: number): string =>
  `成功 ${succeeded} · 失败 ${failed} · 跳过 ${skipped}`

/** 解析失败：{原因或检查文件格式后重试}（edge-states 钉句） */
export const parseFailCopy = (reason: string): string => `解析失败。${reason}。`
