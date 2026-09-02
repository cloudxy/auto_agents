/**
 * 官方网站 - 首页（智能数据采集系统产品页）
 * 章节：Header → Hero → 核心功能 → AI 采集流程 → 系统架构 → CTA → Footer
 * 说明：纯静态展示，不依赖后端接口；管理后台地址经环境变量注入
 */
import React from 'react'
import { Button } from 'antd'
import {
  RocketOutlined,
  LinkOutlined,
  DatabaseOutlined,
  ClusterOutlined,
  DownOutlined,
  ArrowRightOutlined,
} from '@ant-design/icons'
import { motion } from 'framer-motion'
import './Home.css'
import { FadeIn, CONTENT_MAX_WIDTH, EASE_OUT_EXPO } from '../components/home/common'
import FeaturesSection from '../components/home/FeaturesSection'
import AiFlowSection from '../components/home/AiFlowSection'
import ArchitectureSection from '../components/home/ArchitectureSection'
import SkillsSection from '../components/home/SkillsSection'

// 管理后台地址（经环境变量注入，见 .env.development）
const ADMIN_URL = process.env.REACT_APP_ADMIN_URL || 'http://localhost:9112'

const SITE_NAME = 'AutoAgents'
const SITE_SLOGAN = 'AI 驱动的智能数据采集系统'

/** 页头锚点导航 */
const NAV_LINKS = [
  { label: '核心功能', href: '#features' },
  { label: 'AI 采集流程', href: '#ai-flow' },
  { label: '系统架构', href: '#architecture' },
  { label: '技能广场', href: '/skills' },
  { label: '能力广场', href: '/capabilities' },
  { label: '定价', href: '/pricing' },
  { label: '注册', href: '/register' },
]

/** Hero 平台能力概览（静态示意数据） */
const HERO_STATS = [
  { value: '128,000+', label: '累计执行任务', color: '#40a9ff' },
  { value: '12 节点', label: '分布式 Worker 在线', color: '#13c2c2' },
  { value: '3.2 亿条', label: '累计采集数据', color: '#95de64' },
]

/** 平滑滚动到锚点 */
const scrollToAnchor = (href: string) => {
  document.querySelector(href)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

/** 页头：站点标识 + 锚点导航 + 管理后台入口 */
const SiteHeader: React.FC = () => (
  <header
    style={{
      position: 'sticky',
      top: 0,
      zIndex: 1000,
      width: '100%',
      background: 'rgba(255,255,255,0.86)',
      backdropFilter: 'blur(12px)',
      WebkitBackdropFilter: 'blur(12px)',
      borderBottom: '1px solid rgba(18,35,63,0.06)',
    }}
  >
    <div
      style={{
        maxWidth: CONTENT_MAX_WIDTH,
        margin: '0 auto',
        padding: '0 24px',
        height: 64,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div
          style={{
            width: 34,
            height: 34,
            borderRadius: 10,
            background: 'linear-gradient(135deg, #1890ff, #13c2c2)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#fff',
            fontSize: 17,
          }}
        >
          <RocketOutlined />
        </div>
        <span style={{ fontSize: 18, fontWeight: 800, color: '#12233f', letterSpacing: '-0.01em' }}>
          {SITE_NAME}
        </span>
      </div>

      <nav className="header-nav" style={{ display: 'flex', gap: 34 }}>
        {NAV_LINKS.map((l) => (
          <span key={l.href} className="header-nav-link" onClick={() => scrollToAnchor(l.href)}>
            {l.label}
          </span>
        ))}
      </nav>

      <Button type="primary" shape="round" href={ADMIN_URL} icon={<ArrowRightOutlined />}>
        管理后台
      </Button>
    </div>
  </header>
)

/** Hero：产品定位 + 双 CTA + 能力概览（深空指挥中心视觉） */
const Hero: React.FC = () => (
  <section className="hero-section" style={{ padding: '132px 24px 110px' }}>
    {/* 背景装饰：数据网格 + 浮动光晕 */}
    <div className="hero-grid" />
    <div className="hero-glow hero-glow--cyan" />
    <div className="hero-glow hero-glow--blue" />

    {/* 漂浮能力芯片（桌面端） */}
    <div className="hero-chip hero-chip--left">
      <ClusterOutlined style={{ color: '#13c2c2', fontSize: 18 }} />
      分布式 Worker 协同
    </div>
    <div className="hero-chip hero-chip--right">
      <DatabaseOutlined style={{ color: '#40a9ff', fontSize: 18 }} />
      结构化数据落库
    </div>

    <div style={{ maxWidth: 920, margin: '0 auto', textAlign: 'center', position: 'relative' }}>
      <motion.div
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: EASE_OUT_EXPO }}
      >
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            fontSize: 13,
            letterSpacing: '0.2em',
            color: '#7ee7e2',
            background: 'rgba(19,194,194,0.1)',
            border: '1px solid rgba(19,194,194,0.3)',
            borderRadius: 999,
            padding: '7px 18px',
          }}
        >
          <LinkOutlined /> AI-DRIVEN DATA COLLECTION
        </span>
      </motion.div>

      <motion.h1
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
        智能数据采集
        <br />
        <span
          style={{
            background: 'linear-gradient(92deg, #69c0ff 0%, #7ee7e2 55%, #95de64 100%)',
            WebkitBackgroundClip: 'text',
            backgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
          }}
        >
          交给 AI 来完成
        </span>
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
        {SITE_NAME} 是一个 AI 驱动的爬虫管理平台：粘贴目标链接，AI 自动规划采集方案、试采验证并一键上线；
        配合可视化调度与分布式 Worker 集群，让数据获取稳定、高效、全程可控。
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
          onClick={() => scrollToAnchor('#ai-flow')}
          style={{
            height: 54,
            padding: '0 40px',
            fontSize: 16,
            background: 'linear-gradient(92deg, #1890ff, #13c2c2)',
            border: 'none',
            boxShadow: '0 8px 24px rgba(24, 144, 255, 0.4)',
          }}
        >
          体验 AI 采集流程
        </Button>
        <Button
          size="large"
          shape="round"
          ghost
          href={ADMIN_URL}
          style={{
            height: 54,
            padding: '0 36px',
            fontSize: 16,
            color: 'rgba(255,255,255,0.9)',
            borderColor: 'rgba(255,255,255,0.35)',
          }}
        >
          进入管理后台
        </Button>
      </motion.div>

      {/* 平台能力概览 */}
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.7, delay: 0.45, ease: EASE_OUT_EXPO }}
        style={{
          maxWidth: 760,
          margin: '64px auto 0',
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: 16,
        }}
      >
        {HERO_STATS.map((s) => (
          <div key={s.label} className="hero-stat-card">
            <div style={{ fontSize: 'clamp(22px, 3vw, 30px)', fontWeight: 800, color: s.color }}>
              {s.value}
            </div>
            <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.6)', marginTop: 6 }}>{s.label}</div>
          </div>
        ))}
        {/* UX-B7：静态示意数据显式标注，避免被误读为真实运行数据 */}
        <div style={{ gridColumn: '1 / -1', textAlign: 'right', fontSize: 12, color: 'rgba(255,255,255,0.35)' }}>
          * 示意数据，非实时统计
        </div>
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
          打开管理后台，粘贴第一条链接，体验从规划到上线的完整智能采集流程。
        </p>
      </FadeIn>
      <FadeIn delay={0.18}>
        <Button
          type="primary"
          size="large"
          shape="round"
          href={ADMIN_URL}
          icon={<RocketOutlined />}
          style={{
            height: 52,
            padding: '0 38px',
            fontSize: 16,
            marginTop: 32,
            background: 'linear-gradient(92deg, #1890ff, #13c2c2)',
            border: 'none',
            boxShadow: '0 8px 24px rgba(19, 194, 194, 0.35)',
          }}
        >
          立即开始
        </Button>
      </FadeIn>
    </div>
  </section>
)

/** 页脚：站点信息 + 锚点导航 + 版权 */
const SiteFooter: React.FC = () => (
  <footer className="home-footer" style={{ padding: '56px 24px 32px' }}>
    <div
      style={{
        maxWidth: CONTENT_MAX_WIDTH,
        margin: '0 auto',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        flexWrap: 'wrap',
        gap: 24,
      }}
    >
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div
            style={{
              width: 30,
              height: 30,
              borderRadius: 9,
              background: 'linear-gradient(135deg, #1890ff, #13c2c2)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#fff',
              fontSize: 15,
            }}
          >
            <RocketOutlined />
          </div>
          <span style={{ fontSize: 16, fontWeight: 700, color: '#fff' }}>{SITE_NAME}</span>
        </div>
        <p style={{ margin: '12px 0 0', fontSize: 13.5, color: 'rgba(255,255,255,0.45)' }}>
          {SITE_SLOGAN} · 让数据获取稳定、高效、可控
        </p>
      </div>

      <nav style={{ display: 'flex', gap: 28 }}>
        {NAV_LINKS.map((l) => (
          <span key={l.href} className="footer-nav-link" onClick={() => scrollToAnchor(l.href)}>
            {l.label}
          </span>
        ))}
        <a className="footer-nav-link" href={ADMIN_URL} style={{ textDecoration: 'none' }}>
          管理后台
        </a>
      </nav>
    </div>

    <div
      style={{
        maxWidth: CONTENT_MAX_WIDTH,
        margin: '40px auto 0',
        paddingTop: 22,
        borderTop: '1px solid rgba(255,255,255,0.08)',
        textAlign: 'center',
        fontSize: 13,
      }}
    >
      {SITE_NAME} ©2026 Created by xuyun
    </div>
  </footer>
)

/** 首页：多节产品官网页 */
const Home: React.FC = () => {
  return (
    <div style={{ minHeight: '100vh', background: '#fff' }}>
      <SiteHeader />
      <main>
        <Hero />
        <FeaturesSection />
        <AiFlowSection />
        <ArchitectureSection />
        <SkillsSection />
        <CtaBand />
      </main>
      <SiteFooter />
    </div>
  )
}

export default Home
