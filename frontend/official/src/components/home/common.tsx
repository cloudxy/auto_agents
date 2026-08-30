/**
 * 官网首页共用组件与常量
 * FadeIn：基于 framer-motion 的滚动入场动画容器
 * SectionTitle：章节标题（眉标 + 主标题 + 描述）
 */
import React from 'react'
import { motion } from 'framer-motion'

/** 页面内容容器最大宽度 */
export const CONTENT_MAX_WIDTH = 1200

/** 统一入场动效参数（与全站节奏一致） */
export const EASE_OUT_EXPO: [number, number, number, number] = [0.22, 1, 0.36, 1]

interface FadeInProps {
  /** 动画延迟（秒），用于同屏多元素的错峰编排 */
  delay?: number
  /** 垂直位移起点（px） */
  y?: number
  style?: React.CSSProperties
  children: React.ReactNode
}

/**
 * 滚动入场动画容器：进入视口时淡入上浮，只触发一次
 */
export const FadeIn: React.FC<FadeInProps> = ({ delay = 0, y = 28, style, children }) => (
  <motion.div
    initial={{ opacity: 0, y }}
    whileInView={{ opacity: 1, y: 0 }}
    viewport={{ once: true, amount: 0.18 }}
    transition={{ duration: 0.65, delay, ease: EASE_OUT_EXPO }}
    style={style}
  >
    {children}
  </motion.div>
)

interface SectionTitleProps {
  /** 眉标（小标签文字） */
  eyebrow: string
  title: string
  description?: string
  /** 描述文字颜色（默认灰） */
  light?: boolean
  style?: React.CSSProperties
}

/**
 * 章节标题：眉标 → 大标题 → 引导描述，统一全站章节节奏
 */
export const SectionTitle: React.FC<SectionTitleProps> = ({
  eyebrow,
  title,
  description,
  light = false,
  style,
}) => (
  <div style={{ textAlign: 'center', ...style }}>
    <FadeIn>
      <span className="section-eyebrow">{eyebrow}</span>
    </FadeIn>
    <FadeIn delay={0.08}>
      <h2
        style={{
          fontSize: 'clamp(28px, 4vw, 40px)',
          fontWeight: 700,
          letterSpacing: '-0.01em',
          margin: '20px 0 0',
          color: light ? '#fff' : '#12233f',
        }}
      >
        {title}
      </h2>
    </FadeIn>
    {description && (
      <FadeIn delay={0.16}>
        <p
          style={{
            maxWidth: 720,
            margin: '16px auto 0',
            fontSize: 16,
            lineHeight: 1.8,
            color: light ? 'rgba(255,255,255,0.66)' : '#5a6b84',
          }}
        >
          {description}
        </p>
      </FadeIn>
    )}
  </div>
)
