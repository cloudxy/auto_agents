/**
 * T-09（FR-06 / AD-10）：无图资产确定性占位。
 * 规则源 edge-states §8：hash(asset_type+':'+name)%8 → 8 组渐变（深→浅）+ 展示名
 * 首字符 + 右下角类型角标（图标形第二通道，非色相）。回落链：logo → <img onError>
 * → 占位；logo 无值直接占位（GWT-06.2 真图不占位 / 06.3 损坏回落，页面不报错）。
 * 同一资产两次渲染一致（GWT-06.1）由纯函数 visualIndex 保证。
 */
import React, { useEffect, useState } from 'react'
import {
  AppstoreOutlined, CodeOutlined, QuestionOutlined,
  RobotOutlined, TeamOutlined, ThunderboltOutlined,
} from '@ant-design/icons'

import { cardTitle } from './shelfCopy'
import './AssetVisual.css'

/** 与 ImportWizard TYPE_ICONS 同源的四类图标形 + team（货架五类） */
const TYPE_ICONS: Record<string, React.ReactNode> = {
  skill: <ThunderboltOutlined />,
  command: <CodeOutlined />,
  agent: <RobotOutlined />,
  plugin: <AppstoreOutlined />,
  team: <TeamOutlined />,
}

/** djb2 字符串 hash——稳定、无随机源，禁止 Math.random/Date（edge-states §8.1） */
export const hashKey = (key: string): number => {
  let h = 5381
  for (let i = 0; i < key.length; i += 1) {
    h = ((h << 5) + h + key.charCodeAt(i)) >>> 0
  }
  return h >>> 0
}

export const visualKey = (assetType: string, name: string): string => `${assetType}:${name}`

/** 确定性渐变序号 0–7（GWT-06.1 两次渲染一致断言的入口） */
export const visualIndex = (assetType: string, name: string): number =>
  hashKey(visualKey(assetType, name)) % 8

type Props = {
  assetType: string
  name: string
  title?: string | null
  logo?: string | null
  /** card=40×40 r8 / drawer=72×72 r12（edge-states §8.6 尺寸表） */
  size?: 'card' | 'drawer'
}

const AssetVisual: React.FC<Props> = ({ assetType, name, title, logo, size = 'card' }) => {
  const [broken, setBroken] = useState(false)
  useEffect(() => { setBroken(false) }, [logo])
  const showImg = Boolean(logo) && !broken
  if (showImg) {
    return (
      <span className={`asset-visual asset-visual--${size}`} data-testid="asset-visual">
        <img src={logo || ''} alt="" onError={() => setBroken(true)} />
      </span>
    )
  }
  const letter = cardTitle({ title, name }).charAt(0) || name.charAt(0)
  return (
    <span
      className={`asset-visual asset-visual--${size} asset-visual--grad-${visualIndex(assetType, name)}`}
      data-testid="asset-visual"
      data-visual-index={visualIndex(assetType, name)}
      aria-hidden="true"
    >
      <span className="asset-visual__letter">{letter}</span>
      <span className="asset-visual__chip">
        {TYPE_ICONS[assetType] || <QuestionOutlined />}
      </span>
    </span>
  )
}

export default AssetVisual
