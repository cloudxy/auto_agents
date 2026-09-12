/**
 * FR-84 失败≠空 通用态（T-17）：失败句 + 可点「重试」；真 0 空态句 + 可选动作。
 * 句式单一来源——失败走「{名称}加载失败。检查网络后重试。」族，真 0 走「还没有…」；
 * 各屏接入本组件，不发明第二套句式（与 RelayGroups / LlmProviders / Users 已落失败态同款视觉）。
 * 真 0（接口成功且结果为 0）才渲染 LoadEmpty；失败时禁止回落空表或 0（GWT-84.1/84.2）。
 */
import React from 'react'
import { Alert, Button } from 'antd'

interface LoadFailureProps {
  /** FR-84 失败句：「{名称}加载失败。检查网络后重试。」 */
  title: string
  /** 重试按钮回调（react-query 场景传 refetch） */
  onRetry: () => void
  style?: React.CSSProperties
}

/** 页级/卡内加载失败态：失败句 + 可点「重试」 */
export const LoadFailure: React.FC<LoadFailureProps> = ({ title, onRetry, style }) => (
  <Alert
    type="error"
    showIcon
    role="alert"
    style={style}
    title={title}
    action={<Button size="small" onClick={onRetry}>重试</Button>}
  />
)

interface LoadEmptyProps {
  /** 真 0 空态句：「还没有…」 */
  title: string
  action?: React.ReactNode
  style?: React.CSSProperties
}

/** 真 0 空态：空态句 + 可选动作（如「去采集」「创建渠道组」） */
export const LoadEmpty: React.FC<LoadEmptyProps> = ({ title, action, style }) => (
  <Alert type="info" showIcon style={style} title={title} action={action} />
)
