/**
 * 核心功能特性：爬虫配置管理 / 任务调度 / 优先级队列 / 数据管理 / 日志与告警
 */
import React from 'react'
import { Row, Col } from 'antd'
import {
  SettingOutlined,
  ScheduleOutlined,
  UnorderedListOutlined,
  DatabaseOutlined,
  AlertOutlined,
} from '@ant-design/icons'
import { FadeIn, SectionTitle, CONTENT_MAX_WIDTH } from './common'

interface Feature {
  icon: React.ReactNode
  color: string
  tint: string
  title: string
  desc: string
  points: string[]
}

const FEATURES: Feature[] = [
  {
    icon: <SettingOutlined />,
    color: '#1890ff',
    tint: 'rgba(24, 144, 255, 0.09)',
    title: '爬虫配置管理',
    desc: '可视化定义采集站点、解析规则与运行参数，配置中心化托管，一次定义多节点即时生效。',
    points: ['站点与规则版本化', '运行参数热更新'],
  },
  {
    icon: <ScheduleOutlined />,
    color: '#722ed1',
    tint: 'rgba(114, 46, 209, 0.09)',
    title: '任务调度',
    desc: '支持手动触发、定时调度与周期执行，任务状态机全程可观测，失败自动重试。',
    points: ['Cron 定时计划', '状态实时回写'],
  },
  {
    icon: <UnorderedListOutlined />,
    color: '#fa8c16',
    tint: 'rgba(250, 140, 22, 0.1)',
    title: '优先级队列',
    desc: '基于 Redis 的分布式优先级队列，关键任务插队执行，节点扩缩容时调度自动均衡。',
    points: ['多级优先级', '动态负载均衡'],
  },
  {
    icon: <DatabaseOutlined />,
    color: '#13c2c2',
    tint: 'rgba(19, 194, 194, 0.1)',
    title: '数据管理',
    desc: '采集结果结构化入库，内置清洗与去重管线，支持 CSV / Excel 一键导出。',
    points: ['字段级清洗', '多格式导出'],
  },
  {
    icon: <AlertOutlined />,
    color: '#f5222d',
    tint: 'rgba(245, 34, 45, 0.08)',
    title: '日志与告警',
    desc: '全链路日志分级采集，任务失败与节点异常秒级触达，支持 Webhook 多通道通知。',
    points: ['阈值告警规则', '多通道通知'],
  },
]

/**
 * 核心功能区块：3 + 2 的 Bento 式栅格布局，卡片内含能力点标签
 */
const FeaturesSection: React.FC = () => {
  return (
    <section id="features" className="home-section-anchor" style={{ background: '#fff', padding: '104px 24px' }}>
      <div style={{ maxWidth: CONTENT_MAX_WIDTH, margin: '0 auto' }}>
        <SectionTitle
          eyebrow="CORE FEATURES"
          title="一个平台，管好采集全链路"
          description="从配置定义到数据落库，五大核心能力覆盖爬虫生命周期管理，无需在多个工具间来回切换。"
        />

        <Row gutter={[24, 24]} style={{ marginTop: 64 }}>
          {FEATURES.map((f, idx) => (
            <Col key={f.title} xs={24} md={idx < 3 ? 8 : 12}>
              <FadeIn delay={0.08 * idx} style={{ height: '100%' }}>
                <div
                  style={{
                    height: '100%',
                    background: '#fff',
                    border: '1px solid #e8edf3',
                    borderRadius: 20,
                    padding: '28px 26px',
                    boxShadow: '0 10px 30px rgba(20, 42, 76, 0.06)',
                    transition: 'transform .25s ease, box-shadow .25s ease',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.transform = 'translateY(-6px)'
                    e.currentTarget.style.boxShadow = '0 20px 44px rgba(20, 42, 76, 0.12)'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.transform = 'translateY(0)'
                    e.currentTarget.style.boxShadow = '0 10px 30px rgba(20, 42, 76, 0.06)'
                  }}
                >
                  <div
                    style={{
                      width: 52,
                      height: 52,
                      borderRadius: 14,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: 24,
                      color: f.color,
                      background: f.tint,
                    }}
                  >
                    {f.icon}
                  </div>
                  <h3 style={{ fontSize: 19, fontWeight: 700, margin: '18px 0 10px', color: '#12233f' }}>
                    {f.title}
                  </h3>
                  <p style={{ fontSize: 14.5, lineHeight: 1.75, color: '#5a6b84', margin: 0 }}>
                    {f.desc}
                  </p>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 18 }}>
                    {f.points.map((p) => (
                      <span
                        key={p}
                        style={{
                          fontSize: 12,
                          color: f.color,
                          background: f.tint,
                          borderRadius: 999,
                          padding: '4px 12px',
                        }}
                      >
                        {p}
                      </span>
                    ))}
                  </div>
                </div>
              </FadeIn>
            </Col>
          ))}
        </Row>
      </div>
    </section>
  )
}

export default FeaturesSection
