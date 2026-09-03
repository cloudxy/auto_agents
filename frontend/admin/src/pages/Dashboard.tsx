/**
 * Dashboard 首页 - 运行统计仪表盘（阶段 2.1 + B1 质量监控）
 *
 * 数据来源：/admin/stats（SpiderStatsResponse）
 * - 统计卡片：任务总数 / 成功率 / 平均运行时长 / 近 7 日采集结果
 * - 趋势图：近 7 日每日任务数与结果数（折线）
 * - 排行图：各爬虫采集结果量 Top5（条形）
 * - 质量概览：最近任务的质量评分分布（B1）
 */
import React, { useEffect, useState } from 'react'
import { Alert, Typography, Card, Row, Col, Statistic, Button, Empty, Spin, message, Space } from 'antd'
import {
  CheckCircleOutlined, CloseCircleOutlined, ClockCircleOutlined, ThunderboltOutlined,
  SafetyCertificateOutlined, PlusOutlined, RobotOutlined,
} from '@ant-design/icons'
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, Legend, CartesianGrid,
  BarChart, Bar, Cell,
} from 'recharts'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/useAuthStore'
import { fetchAdminStats, fetchQualityReport, fetchRecentCompletedTasks } from '../services/admin'
import { apiErrorMessage } from '../utils/errorMessage'
import { BRAND_TOKENS } from '@auto-agents/frontend-shared'

const { Title } = Typography

interface DailyPoint {
  date: string
  count: number
}

interface Stats {
  total_tasks: number
  pending: number
  running: number
  completed: number
  failed: number
  avg_duration_seconds: number | null
  success_rate: number | null
  total_results: number
  daily_tasks: DailyPoint[]
  daily_results: DailyPoint[]
  top_spiders: { spider_name: string; result_count: number }[]
}

interface QualityReport {
  task_id: number
  avg_score: number | null
  min_score: number | null
  max_score: number | null
  total_items: number
  score_distribution: Record<string, number>
}

const Dashboard: React.FC = () => {
  const { user } = useAuthStore()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [stats, setStats] = useState<Stats | null>(null)
  const [qualityData, setQualityData] = useState<QualityReport | null>(null)
  const [recentTaskIds, setRecentTaskIds] = useState<number[]>([])

  useEffect(() => {
    Promise.all([
      fetchAdminStats<Stats>().then((res) => setStats(res)),
      // 获取最近完成的任务列表，取第一个查质量报告
      fetchRecentCompletedTasks(5)
        .then((ids) => setRecentTaskIds(ids))
        .catch(() => {}),
    ])
      .catch((e) => message.error(apiErrorMessage(e, '获取运行统计失败')))
      .finally(() => setLoading(false))
  }, [])

  // 获取最近任务的质量报告
  useEffect(() => {
    if (recentTaskIds.length === 0) return
    const taskId = recentTaskIds[0]
    fetchQualityReport<QualityReport>(taskId)
      .then((res) => setQualityData(res))
      .catch(() => {})
  }, [recentTaskIds])

  // 近 7 日趋势：把任务数/结果数按日期合并成一行（双折线共用 X 轴）
  const trendData = (() => {
    if (!stats) return []
    const map: Record<string, { date: string; tasks: number; results: number }> = {}
    for (const p of stats.daily_tasks || []) map[p.date] = { date: p.date.slice(5), tasks: p.count, results: 0 }
    for (const p of stats.daily_results || []) {
      const key = p.date.slice(5)
      if (map[p.date]) map[p.date].results = p.count
      else map[p.date] = { date: key, tasks: 0, results: p.count }
    }
    return Object.values(map).sort((a, b) => a.date.localeCompare(b.date))
  })()

  const successRate = stats?.success_rate != null ? `${(stats.success_rate * 100).toFixed(1)}%` : '-'
  const avgDuration = stats?.avg_duration_seconds != null ? `${stats.avg_duration_seconds.toFixed(1)}s` : '-'

  return (
    <div style={{ padding: 0 }}>
      {/* UX2（工单 90）：新用户 onboarding——零任务时三步快速开始引导 */}
      {!loading && stats && (stats.total_tasks ?? 0) === 0 && (
        <Alert type="info" showIcon style={{ marginBottom: 16 }}
               message="从这里开始你的第一次智能采集（三步）"
               description={
                 <ol style={{ margin: '8px 0 0', paddingLeft: 20, lineHeight: 2 }}>
                   <li>
                     配置 LLM 供应商（AI 规划的"大脑"）：前往
                     <Button type="link" size="small" style={{ padding: 0 }} onClick={() => navigate('/llm')}>LLM 配置</Button>
                     添加 Key 并激活
                   </li>
                   <li>
                     创建第一个采集任务：在
                     <Button type="link" size="small" style={{ padding: 0 }} onClick={() => navigate('/spiders/tasks')}>采集任务</Button>
                     页选择爬虫并提交
                   </li>
                   <li>
                     或直接体验 <Button type="link" size="small" style={{ padding: 0 }} onClick={() => navigate('/ai')}>AI 采集规划</Button>
                     ：粘贴链接，AI 自动生成方案、试采并上线
                   </li>
                 </ol>
               }
        />
      )}
      {/* U1-4：行动入口（原第二套页头已移除——AdminLayout 已有全局页头与退出登录） */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }} align="middle">
        <Col flex="auto">
          <Title level={4} style={{ margin: 0 }}>
            欢迎回来{user?.username ? `，${user.username}` : ''}
          </Title>
        </Col>
        <Col>
          <Space>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/spiders/tasks')}>
              创建采集任务
            </Button>
            <Button icon={<RobotOutlined />} onClick={() => navigate('/ai')}>
              AI 智能采集
            </Button>
          </Space>
        </Col>
      </Row>

      <Spin spinning={loading}>
          {/* 统计卡片 */}
          <Row gutter={[16, 16]}>
            <Col xs={12} md={6}>
              <Card>
                <Statistic
                  title="任务总数"
                  value={stats?.total_tasks ?? 0}
                  prefix={<ThunderboltOutlined />}
                  suffix={
                    <span style={{ fontSize: 12, color: '#999' }}>
                      运行中 {stats?.running ?? 0} / 待执行 {stats?.pending ?? 0}
                    </span>
                  }
                />
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card>
                <Statistic
                  title="成功率"
                  value={successRate}
                  prefix={<CheckCircleOutlined />}
                  valueStyle={{ color: '#3f8600' }}
                  suffix={
                    <span style={{ fontSize: 12, color: '#cf1322' }}>
                      失败 <CloseCircleOutlined /> {stats?.failed ?? 0}
                    </span>
                  }
                />
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card>
                <Statistic
                  title="平均运行时长"
                  value={avgDuration}
                  prefix={<ClockCircleOutlined />}
                />
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card>
                <Statistic
                  title="近 7 日采集结果"
                  value={stats?.total_results ?? 0}
                  suffix={<span style={{ fontSize: 12, color: '#999' }}>条</span>}
                />
              </Card>
            </Col>
          </Row>

          {/* 趋势图 + 排行图 */}
          <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
            <Col xs={24} lg={14}>
              <Card title="近 7 日运行趋势">
                {trendData.length ? (
                  <ResponsiveContainer width="100%" height={280}>
                    <LineChart data={trendData} margin={{ top: 8, right: 16 }}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="date" />
                      <YAxis allowDecimals={false} />
                      <Tooltip />
                      <Legend />
                      <Line type="monotone" dataKey="tasks" name="任务数" stroke={BRAND_TOKENS.primary} strokeWidth={2} />
                      <Line type="monotone" dataKey="results" name="结果数" stroke="#52c41a" strokeWidth={2} />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <Empty description="近 7 日暂无运行数据" />
                )}
              </Card>
            </Col>
            <Col xs={24} lg={10}>
              <Card title="采集结果 Top5">
                {(stats?.top_spiders || []).length ? (
                  <ResponsiveContainer width="100%" height={280}>
                    <BarChart
                      data={stats!.top_spiders}
                      layout="vertical"
                      margin={{ top: 8, right: 24, left: 8 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis type="number" allowDecimals={false} />
                      <YAxis type="category" dataKey="spider_name" width={110} />
                      <Tooltip />
                      <Bar dataKey="result_count" name="结果条数" fill="#722ed1" barSize={18} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <Empty description="暂无采集结果" />
                )}
              </Card>
            </Col>
          </Row>

          {/* 质量概览（B1） */}
          <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
            <Col xs={24} lg={10}>
              <Card title={<span><SafetyCertificateOutlined style={{ marginRight: 8 }} />数据质量概览</span>}>
                {qualityData && qualityData.total_items > 0 ? (
                  <>
                    <Row gutter={16}>
                      <Col span={8}>
                        <Statistic
                          title="平均评分"
                          value={qualityData.avg_score ?? '-'}
                          suffix="/ 100"
                          valueStyle={{ color: (qualityData.avg_score ?? 0) >= 60 ? '#3f8600' : '#cf1322' }}
                        />
                      </Col>
                      <Col span={8}>
                        <Statistic title="最低分" value={qualityData.min_score ?? '-'} suffix="/ 100" />
                      </Col>
                      <Col span={8}>
                        <Statistic title="最高分" value={qualityData.max_score ?? '-'} suffix="/ 100" />
                      </Col>
                    </Row>
                    <div style={{ marginTop: 12, fontSize: 12, color: '#999' }}>
                      基于最近完成任务 #{qualityData.task_id}（{qualityData.total_items} 条数据）
                    </div>
                  </>
                ) : (
                  <Empty description="暂无质量评分数据" />
                )}
              </Card>
            </Col>
            <Col xs={24} lg={14}>
              <Card title="质量分布">
                {qualityData && qualityData.total_items > 0 ? (
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart
                      data={[
                        { name: '优秀(80-100)', count: qualityData.score_distribution['excellent(80-100)'] || 0 },
                        { name: '良好(60-80)', count: qualityData.score_distribution['good(60-80)'] || 0 },
                        { name: '一般(40-60)', count: qualityData.score_distribution['fair(40-60)'] || 0 },
                        { name: '较差(0-40)', count: qualityData.score_distribution['poor(0-40)'] || 0 },
                      ]}
                      margin={{ top: 8, right: 16, left: 8 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="name" fontSize={12} />
                      <YAxis allowDecimals={false} />
                      <Tooltip />
                      <Bar dataKey="count" name="数据条数" barSize={36}>
                        <Cell fill="#52c41a" />
                        <Cell fill={BRAND_TOKENS.primary} />
                        <Cell fill="#faad14" />
                        <Cell fill="#ff4d4f" />
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <Empty description="暂无质量分布数据" />
                )}
              </Card>
            </Col>
          </Row>
      </Spin>
    </div>
  )
}

export default Dashboard
