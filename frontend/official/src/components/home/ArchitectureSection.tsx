/**
 * 系统架构示意：管理后台 → 调度队列 → 分布式爬虫 Worker → 数据存储
 * 纯 CSS 管线容器呈现，桌面横向管线 / 移动端纵向堆叠
 */
import React from 'react'
import {
  DesktopOutlined,
  NodeIndexOutlined,
  ClusterOutlined,
  DatabaseOutlined,
} from '@ant-design/icons'
import { FadeIn, SectionTitle, CONTENT_MAX_WIDTH } from './common'

interface ArchNode {
  icon: React.ReactNode
  color: string
  tint: string
  title: string
  subtitle: string
  items: string[]
}

const ARCH_NODES: ArchNode[] = [
  {
    icon: <DesktopOutlined />,
    color: 'var(--site-primary, #1677ff)',
    tint: 'rgba(24, 144, 255, 0.09)',
    title: '管理后台',
    subtitle: '可视化控制台',
    items: ['RBAC 权限管控', '任务与节点监控', '系统参数配置'],
  },
  {
    icon: <NodeIndexOutlined />,
    color: '#722ed1',
    tint: 'rgba(114, 46, 209, 0.09)',
    title: '调度队列',
    subtitle: 'FastAPI + Redis',
    items: ['优先级任务队列', '定时调度计划', '失败重试分发'],
  },
  {
    icon: <ClusterOutlined />,
    color: '#13c2c2',
    tint: 'rgba(19, 194, 194, 0.1)',
    title: '分布式爬虫 Worker',
    subtitle: 'Scrapy-Redis 集群',
    items: ['UA / 代理轮换', '多节点协同', '横向弹性扩容'],
  },
  {
    icon: <DatabaseOutlined />,
    color: '#52c41a',
    tint: 'rgba(82, 196, 26, 0.09)',
    title: '数据存储',
    subtitle: '结构化落库',
    items: ['MySQL 主存储', 'Redis 队列缓存', '导出中心'],
  },
]

/** 技术栈标签 */
const TECH_TAGS = ['React', 'FastAPI', 'Scrapy-Redis', 'MySQL', 'Redis', 'Docker']

/** Worker 集群示意小方块（第三节点内部呈现多节点） */
const WorkerCluster = () => (
  <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
    {['A', 'B', 'C'].map((n) => (
      <div key={n} className="worker-cell">
        Worker {n}
      </div>
    ))}
  </div>
)

/**
 * 架构示意区块：四层横向管线 + 流动虚线连接，底部罗列技术栈标签
 */
const ArchitectureSection: React.FC = () => {
  return (
    <section id="architecture" className="home-section-anchor" style={{ background: '#fff', padding: '104px 24px' }}>
      <div style={{ maxWidth: CONTENT_MAX_WIDTH, margin: '0 auto' }}>
        <SectionTitle
          eyebrow="SYSTEM ARCHITECTURE"
          title="分布式管线式架构"
          description="指令从控制台一路流向数据存储，每一层职责单一、独立扩展，任一节点故障不影响整体采集。"
        />

        <FadeIn delay={0.1} style={{ marginTop: 72 }}>
          <div className="arch-pipeline">
            {ARCH_NODES.map((node, idx) => (
              <React.Fragment key={node.title}>
                <div className="arch-node">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <div
                      style={{
                        width: 46,
                        height: 46,
                        borderRadius: 13,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: 21,
                        color: node.color,
                        background: node.tint,
                        flex: 'none',
                      }}
                    >
                      {node.icon}
                    </div>
                    <div>
                      <div style={{ fontSize: 16.5, fontWeight: 700, color: '#12233f' }}>{node.title}</div>
                      <div style={{ fontSize: 12.5, color: '#8494ab', marginTop: 2 }}>{node.subtitle}</div>
                    </div>
                  </div>

                  <ul style={{ margin: '16px 0 0', padding: 0, listStyle: 'none' }}>
                    {node.items.map((item) => (
                      <li
                        key={item}
                        style={{
                          fontSize: 13.5,
                          color: '#4a5b74',
                          lineHeight: 2,
                          display: 'flex',
                          alignItems: 'center',
                          gap: 8,
                        }}
                      >
                        <span
                          style={{
                            width: 5,
                            height: 5,
                            borderRadius: '50%',
                            background: node.color,
                            flex: 'none',
                          }}
                        />
                        {item}
                      </li>
                    ))}
                  </ul>

                  {/* 第三层呈现 Worker 集群形态 */}
                  {idx === 2 && <WorkerCluster />}
                </div>

                {/* 层间连接箭头（移动端自动转纵向） */}
                {idx < ARCH_NODES.length - 1 && <div className="arch-connector" />}
              </React.Fragment>
            ))}
          </div>
        </FadeIn>

        <FadeIn delay={0.18}>
          <div
            style={{
              marginTop: 56,
              display: 'flex',
              flexWrap: 'wrap',
              justifyContent: 'center',
              alignItems: 'center',
              gap: 12,
            }}
          >
            <span style={{ fontSize: 13, color: '#8494ab', letterSpacing: '0.1em' }}>技术栈</span>
            {TECH_TAGS.map((t) => (
              <span key={t} className="tech-tag">
                {t}
              </span>
            ))}
          </div>
        </FadeIn>
      </div>
    </section>
  )
}

export default ArchitectureSection
