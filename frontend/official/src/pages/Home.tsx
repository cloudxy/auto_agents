/**
 * 官方网站 - 首页（智能数据采集系统产品页）
 * 章节：Hero → 核心功能 → AI 采集流程 → 系统架构 → CTA（Header/Footer 归 SiteLayout，工单 70）
 * 说明：Hero/功能介绍/定价入口为静态诚实文案；能力精选依赖公开列表；管理后台地址经环境变量注入
 */
import React from 'react'
import { Button, message } from 'antd'
import {
  RocketOutlined,
  LinkOutlined,
  DatabaseOutlined,
  ClusterOutlined,
  DownOutlined,
} from '@ant-design/icons'
import { motion } from 'framer-motion'
import './Home.css'
import { FadeIn, CONTENT_MAX_WIDTH, EASE_OUT_EXPO } from '../components/home/common'
import FeaturesSection from '../components/home/FeaturesSection'
import AiFlowSection from '../components/home/AiFlowSection'
import ArchitectureSection from '../components/home/ArchitectureSection'
import SkillsSection from '../components/home/SkillsSection'
import { trackCta } from '../services/beacon'

// 管理后台地址（经环境变量注入，见 .env.development）
const ADMIN_URL = process.env.REACT_APP_ADMIN_URL || 'http://localhost:9112'

const SITE_NAME = 'AutoAgents'
/** FR-U04 / GWT-U04.1：首屏第一句锁采集。支付/中转不得顶替。 */
export const HERO_FIRST_SENTENCE = '粘贴链接即可出数。'
const TOUCH_TARGET_STYLE: React.CSSProperties = {
  minHeight: 'var(--size-touch, 44px)',
  minWidth: 'var(--size-touch, 44px)',
}

const warnOfflineRegister = (event: React.MouseEvent) => {
  if (typeof navigator !== 'undefined' && !navigator.onLine) {
    event.preventDefault()
    message.warning('网络不可用。连接恢复后再注册。')
  }
}

/** Hero：产品定位 + 双 CTA + 能力概览（深空指挥中心视觉） */
const Hero: React.FC = () => (
  <section
    className="hero-section"
    data-testid="hero-section"
    aria-labelledby="hero-title"
    style={{ padding: '132px 24px 110px' }}
  >
    {/* 背景装饰：数据网格 + 浮动光晕 */}
    <div className="hero-grid" />
    <div className="hero-glow hero-glow--cyan" />
    <div className="hero-glow hero-glow--blue" />

    {/* 漂浮能力芯片（桌面端） */}
    <div className="hero-chip hero-chip--left" aria-hidden="true">
      <ClusterOutlined style={{ color: 'var(--site-accent, #13c2c2)', fontSize: 18 }} />
      分布式 Worker 协同
    </div>
    <div className="hero-chip hero-chip--right" aria-hidden="true">
      <DatabaseOutlined style={{ color: 'var(--site-primary, #1677ff)', fontSize: 18 }} />
      结构化数据落库
    </div>

    <div style={{ maxWidth: 920, margin: '0 auto', textAlign: 'center', position: 'relative' }}>
      <motion.div
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: EASE_OUT_EXPO }}
      >
        <span
          aria-hidden="true"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            fontSize: 13,
            letterSpacing: '0.2em',
            color: 'var(--site-accent, #13c2c2)',
            background: 'rgba(19,194,194,0.1)',
            border: '1px solid rgba(19,194,194,0.3)',
            borderRadius: 'var(--radius-pill, 999px)',
            padding: '7px 18px',
          }}
        >
          <LinkOutlined /> AI-DRIVEN DATA COLLECTION
        </span>
      </motion.div>

      <motion.h1
        id="hero-title"
        data-testid="hero-first-sentence"
        initial={{ opacity: 0, y: 26 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.7, delay: 0.1, ease: EASE_OUT_EXPO }}
        style={{
          fontSize: 'clamp(34px, 5.6vw, 60px)',
          fontWeight: 800,
          lineHeight: 1.18,
          letterSpacing: '-0.015em',
          margin: '28px 0 0',
        }}
      >
        {HERO_FIRST_SENTENCE}
        <br />
        <span className="hero-title-accent">智能数据采集</span>
      </motion.h1>

      <motion.p
        initial={{ opacity: 0, y: 26 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.7, delay: 0.2, ease: EASE_OUT_EXPO }}
        style={{
          maxWidth: 680,
          margin: '24px auto 0',
          fontSize: 17.5,
          lineHeight: 1.85,
          color: 'rgba(255,255,255,0.68)',
        }}
      >
        {SITE_NAME} 把采集控制面摊开：粘贴链接、提交任务、查看结果。
        AI 规划与试采帮你走完从链接到入库；没有真实聚合时不展示规模数字。
      </motion.p>

      <motion.div
        initial={{ opacity: 0, y: 26 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.7, delay: 0.3, ease: EASE_OUT_EXPO }}
        style={{ display: 'flex', justifyContent: 'center', gap: 16, marginTop: 44, flexWrap: 'wrap' }}
      >
        <Button
          type="primary"
          size="large"
          shape="round"
          icon={<RocketOutlined />}
          href="/register"
          onClick={warnOfflineRegister}
          className="site-touch-target hero-cta-primary"
          style={{
            ...TOUCH_TARGET_STYLE,
            height: 54,
            padding: '0 40px',
            fontSize: 16,
            background: 'linear-gradient(92deg, var(--site-primary, #1677ff), var(--site-accent, #13c2c2))',
            border: 'none',
            boxShadow: '0 8px 24px rgba(24, 144, 255, 0.4)',
          }}
        >
          免费注册
        </Button>
        <Button
          size="large"
          shape="round"
          ghost
          href={`${ADMIN_URL}/login`}
          data-cta="enter_admin"
          onClick={() => trackCta('enter_admin')}
          style={{
            height: 54,
            padding: '0 36px',
            fontSize: 16,
            color: 'rgba(255,255,255,0.9)',
            borderColor: 'rgba(255,255,255,0.35)',
          }}
        >
          登录管理后台
        </Button>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.4, ease: EASE_OUT_EXPO }}
        style={{ marginTop: 20 }}
      >
        <Button
          type="link"
          data-cta="try_ai_flow"
          onClick={() => {
            trackCta('try_ai_flow')
            document.getElementById('ai-flow')?.scrollIntoView({ behavior: 'smooth' })
          }}
          style={{ color: 'rgba(255,255,255,0.72)' }}
        >
          体验 AI 采集流程
        </Button>
      </motion.div>
    </div>

    {/* 滚动提示 */}
    <div className="hero-scroll-hint">
      <DownOutlined />
    </div>
  </section>
)

/** 底部行动号召带 */
const CtaBand: React.FC = () => (
  <section className="cta-band" style={{ padding: '88px 24px' }}>
    <div style={{ maxWidth: CONTENT_MAX_WIDTH, margin: '0 auto', textAlign: 'center', position: 'relative' }}>
      <FadeIn>
        <h2 style={{ fontSize: 'clamp(26px, 3.6vw, 36px)', fontWeight: 800, margin: 0 }}>
          准备好让数据采集跑起来了吗？
        </h2>
      </FadeIn>
      <FadeIn delay={0.1}>
        <p style={{ margin: '16px auto 0', maxWidth: 560, fontSize: 16, lineHeight: 1.8, color: 'rgba(255,255,255,0.66)' }}>
          免费注册后即可粘贴链接、提交任务并查看结果。专业档与企业档尚未开通购买。
        </p>
      </FadeIn>
      <FadeIn delay={0.18}>
        <Button
          type="primary"
          size="large"
          shape="round"
          href="/register"
          onClick={warnOfflineRegister}
          icon={<RocketOutlined />}
          className="site-touch-target"
          style={{
            ...TOUCH_TARGET_STYLE,
            height: 52,
            padding: '0 38px',
            fontSize: 16,
            marginTop: 32,
            background: 'linear-gradient(92deg, var(--site-primary, #1677ff), #13c2c2)',
            border: 'none',
            boxShadow: '0 8px 24px rgba(19, 194, 194, 0.35)',
          }}
        >
          免费注册
        </Button>
      </FadeIn>
    </div>
  </section>
)

/** 首页：多节产品官网页 */
const Home: React.FC = () => {
  return (
    <div style={{ background: '#fff' }}>
      <main>
        <Hero />
        <FeaturesSection />
        <AiFlowSection />
        <ArchitectureSection />
        <SkillsSection />
        <CtaBand />
      </main>
    </div>
  )
}

export default Home
