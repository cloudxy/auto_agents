/**
 * 官网站点布局（工单 70）：深色实底 Header + Footer + Outlet
 *
 * 消除 4 页各自重复的头部条；Header 导航全为路由内链（Link），
 * 不再做 document.querySelector 锚点定位（该路径曾因路由链接被当
 * 选择器而抛 SyntaxError）。
 */
import React from 'react'
import { Link, Outlet, useLocation } from 'react-router-dom'
import { Button } from 'antd'
import { RocketOutlined, ArrowRightOutlined } from '@ant-design/icons'

const ADMIN_URL = process.env.REACT_APP_ADMIN_URL || 'http://localhost:9112'

const SITE_NAME = 'AutoAgents'
const SITE_SLOGAN = 'AI 驱动的智能数据采集系统'

/** 顶部导航（路由内链） */
const NAV_LINKS = [
  { label: '技能广场', to: '/skills' },
  { label: '能力广场', to: '/capabilities' },
  { label: '定价', to: '/pricing' },
  { label: '注册', to: '/register' },
]

const linkStyle: React.CSSProperties = {
  color: 'rgba(255,255,255,0.78)',
  fontSize: 14,
  textDecoration: 'none',
}
const linkActiveStyle: React.CSSProperties = { ...linkStyle, color: '#fff', fontWeight: 600 }

const SiteLayout: React.FC = () => {
  const { pathname } = useLocation()
  return (
    <div style={{ minHeight: '100vh', background: '#f7f9fc', display: 'flex', flexDirection: 'column' }}>
      <header
        style={{
          position: 'sticky', top: 0, zIndex: 1000, width: '100%',
          background: '#001529',
          borderBottom: '1px solid rgba(255,255,255,0.08)',
        }}
      >
        <div
          style={{
            maxWidth: 1200, margin: '0 auto', padding: '0 16px', minHeight: 60, flexWrap: 'wrap',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          }}
        >
          <Link to="/" style={{ display: 'flex', alignItems: 'center', gap: 10, textDecoration: 'none' }}>
            <span
              style={{
                width: 32, height: 32, borderRadius: 9,
                background: 'linear-gradient(135deg, var(--site-primary, #1677ff), #13c2c2)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: '#fff', fontSize: 16,
              }}
            >
              <RocketOutlined aria-hidden />
            </span>
            <span style={{ fontSize: 17, fontWeight: 800, color: '#fff', letterSpacing: '-0.01em' }}>
              {SITE_NAME}
            </span>
          </Link>

          <nav aria-label="站内导航" style={{ display: 'flex', gap: 26, flexWrap: 'wrap' }}>
            {NAV_LINKS.map((l) => (
              <Link
                key={l.to}
                to={l.to}
                style={pathname === l.to ? linkActiveStyle : linkStyle}
              >
                {l.label}
              </Link>
            ))}
          </nav>

          <Button type="primary" shape="round" href={ADMIN_URL} icon={<ArrowRightOutlined aria-hidden />}>
            管理后台
          </Button>
        </div>
      </header>

      <main style={{ flex: 1 }}>
        <Outlet />
      </main>

      <footer style={{ background: '#001529', padding: '48px 24px 28px' }}>
        <div
          style={{
            maxWidth: 1200, margin: '0 auto',
            display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
            flexWrap: 'wrap', gap: 24,
          }}
        >
          <div>
            <div style={{ fontSize: 15, fontWeight: 700, color: '#fff' }}>{SITE_NAME}</div>
            <p style={{ margin: '10px 0 0', fontSize: 13, color: 'rgba(255,255,255,0.45)' }}>
              {SITE_SLOGAN} · 让数据获取稳定、高效、可控
            </p>
          </div>
          <nav aria-label="页脚导航" style={{ display: 'flex', gap: 22, flexWrap: 'wrap' }}>
            {NAV_LINKS.map((l) => (
              <Link key={l.to} to={l.to} style={linkStyle}>{l.label}</Link>
            ))}
          </nav>
        </div>
        <div
          style={{
            maxWidth: 1200, margin: '32px auto 0', paddingTop: 20,
            borderTop: '1px solid rgba(255,255,255,0.08)',
            textAlign: 'center', fontSize: 12.5, color: 'rgba(255,255,255,0.4)',
          }}
        >
          {SITE_NAME} ©2026 Created by xuyun
        </div>
      </footer>
    </div>
  )
}

export default SiteLayout
