/**
 * AI 智能采集流程演示：粘贴链接 → AI 规划方案 → 自动试采验证 → 一键上线
 * 每一步配一个纯 CSS 迷你模拟界面，直观呈现产品交互
 */
import React from 'react'
import {
  LinkOutlined,
  RobotOutlined,
  FileSearchOutlined,
  CloudUploadOutlined,
  CheckOutlined,
} from '@ant-design/icons'
import { FadeIn, SectionTitle, CONTENT_MAX_WIDTH } from './common'

interface FlowStep {
  no: string
  icon: React.ReactNode
  color: string
  gradient: string
  title: string
  desc: string
}

const FLOW_STEPS: FlowStep[] = [
  {
    no: '01',
    icon: <LinkOutlined />,
    color: '#1890ff',
    gradient: 'linear-gradient(135deg, #1890ff, #40a9ff)',
    title: '粘贴链接',
    desc: '输入目标页面地址，用一句话描述你想提取的字段，无需编写任何代码。',
  },
  {
    no: '02',
    icon: <RobotOutlined />,
    color: '#722ed1',
    gradient: 'linear-gradient(135deg, #722ed1, #9254de)',
    title: 'AI 规划方案',
    desc: 'AI 自动分析页面结构，生成选择器、翻页策略与反爬应对方案。',
  },
  {
    no: '03',
    icon: <FileSearchOutlined />,
    color: '#fa8c16',
    gradient: 'linear-gradient(135deg, #fa8c16, #ffc069)',
    title: '自动试采验证',
    desc: '小批量试运行采集，预览真实数据样本，自动校验字段完整性。',
  },
  {
    no: '04',
    icon: <CloudUploadOutlined />,
    color: '#52c41a',
    gradient: 'linear-gradient(135deg, #52c41a, #95de64)',
    title: '一键上线',
    desc: '确认方案后发布至分布式节点，进入正式调度，数据持续稳定入库。',
  },
]

/** 步骤一模拟界面：URL 输入框 + 字段提示 */
const MockInput = () => (
  <div className="mock-panel">
    <div style={{ color: '#8494ab', marginBottom: 8 }}>目标地址</div>
    <div className="mock-input">
      <LinkOutlined style={{ color: '#1890ff', flex: 'none' }} />
      <span>https://example.com/news</span>
      <span className="mock-caret" />
    </div>
    <div style={{ display: 'flex', gap: 6, marginTop: 10, flexWrap: 'wrap' }}>
      {['标题', '发布日期', '正文摘要'].map((t) => (
        <span
          key={t}
          style={{
            fontSize: 11,
            color: '#1890ff',
            background: 'rgba(24,144,255,0.08)',
            border: '1px solid rgba(24,144,255,0.25)',
            borderRadius: 999,
            padding: '2px 9px',
          }}
        >
          {t}
        </span>
      ))}
    </div>
  </div>
)

/** 步骤二模拟界面：AI 生成的采集方案（骨架 + 选择器代码） */
const MockPlan = () => (
  <div className="mock-panel">
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
      <RobotOutlined style={{ color: '#722ed1' }} />
      <span style={{ color: '#33465e', fontWeight: 600 }}>采集方案已生成</span>
    </div>
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 10 }}>
      <div className="mock-line" style={{ width: '86%' }} />
      <div className="mock-line" style={{ width: '64%' }} />
      <div className="mock-line" style={{ width: '74%' }} />
    </div>
    <div className="mock-code">.news-list &gt; .item .title</div>
  </div>
)

/** 步骤三模拟界面：试采样本预览表 + 校验通过徽章 */
const MockPreview = () => (
  <div className="mock-panel">
    <table className="mock-table">
      <tbody>
        <tr>
          <td>标题</td>
          <td>智能体行业年报发布</td>
        </tr>
        <tr>
          <td>日期</td>
          <td>2026-08-21</td>
        </tr>
        <tr>
          <td>摘要</td>
          <td>多家机构联合发布行业…</td>
        </tr>
      </tbody>
    </table>
    <div style={{ marginTop: 10 }}>
      <span className="mock-badge mock-badge--ok">
        <CheckOutlined /> 字段校验通过
      </span>
    </div>
  </div>
)

/** 步骤四模拟界面：发布状态徽章 + 节点在线脉冲点 */
const MockLaunch = () => (
  <div className="mock-panel">
    <div style={{ color: '#8494ab', marginBottom: 10 }}>发布目标</div>
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {['Worker 节点 A', 'Worker 节点 B', 'Worker 节点 C'].map((n) => (
        <div
          key={n}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            border: '1px solid #e6edf5',
            borderRadius: 8,
            padding: '6px 10px',
            color: '#4a5b74',
          }}
        >
          <span>{n}</span>
          <span className="mock-pulse-dot" />
        </div>
      ))}
    </div>
    <div style={{ marginTop: 10 }}>
      <span className="mock-badge mock-badge--live">已进入正式调度</span>
    </div>
  </div>
)

const STEP_MOCKS: React.ReactNode[] = [<MockInput />, <MockPlan />, <MockPreview />, <MockLaunch />]

/**
 * AI 采集流程区块：桌面横向四步 + 虚线流动连接，移动端自动转纵向
 */
const AiFlowSection: React.FC = () => {
  return (
    <section
      id="ai-flow"
      className="home-section-anchor"
      style={{ background: 'linear-gradient(180deg, #f6f8fc 0%, #eef3fa 100%)', padding: '104px 24px' }}
    >
      <div style={{ maxWidth: CONTENT_MAX_WIDTH, margin: '0 auto' }}>
        <SectionTitle
          eyebrow="AI-POWERED WORKFLOW"
          title="从一条链接到上线，只要四步"
          description="把复杂的爬虫工程交给 AI：你负责描述需求，平台负责规划、验证与运行。"
        />

        <div className="ai-flow-track" style={{ marginTop: 72 }}>
          {FLOW_STEPS.map((step, idx) => (
            <div key={step.no} className="ai-flow-step">
              <FadeIn delay={0.1 * idx}>
                {/* 步骤编号与图标 */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 20 }}>
                  <div className="ai-step-no" style={{ background: step.gradient }}>
                    {step.icon}
                  </div>
                  <span
                    style={{
                      fontSize: 30,
                      fontWeight: 800,
                      letterSpacing: '0.04em',
                      color: 'rgba(18, 35, 63, 0.14)',
                    }}
                  >
                    {step.no}
                  </span>
                </div>

                {/* 迷你模拟界面 */}
                <div style={{ marginBottom: 18 }}>{STEP_MOCKS[idx]}</div>

                {/* 步骤说明 */}
                <h3 style={{ fontSize: 18, fontWeight: 700, margin: '0 0 8px', color: '#12233f' }}>
                  {step.title}
                </h3>
                <p style={{ fontSize: 14, lineHeight: 1.75, color: '#5a6b84', margin: 0 }}>{step.desc}</p>
              </FadeIn>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

export default AiFlowSection
