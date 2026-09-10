/**
 * 能力资产域展示常量（工单 66：4 处 TIER_COLORS 定义收敛）
 */

/** Tier → antd Tag 色值 */
export const TIER_COLORS: Record<string, string> = {
  S: 'gold',
  A: 'green',
  B: 'blue',
  C: 'default',
}

/** Tier → 中文标签 */
export const TIER_LABELS: Record<string, string> = {
  S: 'S 级',
  A: 'A 级',
  B: 'B 级',
  C: 'C 级',
}

/** 资产类型 → 中文标签（公开五类；expert 一周期映射为智能体） */
export const ASSET_TYPE_LABELS: Record<string, string> = {
  skill: '技能',
  plugin: '插件',
  command: '命令',
  agent: '智能体',
  team: '专家团',
  expert: '智能体',
  expert_team: '专家团',
}
