/**
 * 语义设计令牌（工单 77 / D7）：两应用共用的品牌语义色单源
 *
 * - antd 应用（admin）经 ConfigProvider theme token 消费
 * - official 在 tokens.css 映射为 --site-* CSS 变量（内联样式可用 var() 引用）
 * 禁止在业务代码硬编码色值（F-4 黑名单：#1890ff 等历史遗留蓝）
 */
export const BRAND_TOKENS = {
  /** 主色（antd v6 默认蓝，品牌换色只改此处） */
  primary: '#1677ff',
  /** 强调青（渐变副色） */
  accent: '#13c2c2',
  /** 成功 */
  success: '#52c41a',
  /** 警告 */
  warning: '#faad14',
  /** 危险 */
  danger: '#ff4d4f',
  /** 深空底（官方页 hero/footer） */
  deepSpace: '#001529',
} as const

export type BrandTokenKey = keyof typeof BRAND_TOKENS
