/**
 * AI 采集向导步骤内容（从 pages/AiPlans.tsx 拆出，期 4 前端治理）
 *
 * 渲染三步向导的步骤条与当前步骤内容：
 * ① 创建计划表单 ② 方案预览与本地微调 ③ 试采历史对比与一键上线。
 * 状态与动作由 useAiPlanFlow 提供（props.flow），抽屉开关由页面注入。
 */
import React from 'react'
import {
  Alert, Button, Collapse, Empty, Form, Input, InputNumber, Select, Space,
  Steps, Table, Tag, Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  ReloadOutlined, RocketOutlined, ExperimentOutlined,
  EditOutlined, FileTextOutlined, EyeOutlined, ThunderboltOutlined, CheckCircleOutlined,
} from '@ant-design/icons'
import { AI_PLAN_STATUS_META } from '../../services/ai'
import type { AiPlanTestHistory } from '../../services/ai'
import { SelectorRowList } from '../spider/formUtils'
import { STATUS_META } from '../spider/types'
import type { Task } from '../spider/types'
import { FilterRuleList, FlowPreview } from './PlanForm'
import type { AiPlanFlow } from '../../hooks/useAiPlanFlow'

const { Text } = Typography

interface PlanDetailProps {
  /** 向导状态机（useAiPlanFlow 返回值） */
  flow: AiPlanFlow
  /** 规划/试采/上线操作权限（与创建共享 operator 权限） */
  canOperate: boolean
  /** 打开试采日志抽屉（页面注入） */
  onOpenLog: (taskId: number, status: string, resultCount?: number) => void
  /** 打开试采结果抽屉（页面注入） */
  onOpenResult: (taskId: number, status: string, resultCount?: number) => void
}

// ---------------- 试采历史列 ----------------
const historyColumns: ColumnsType<AiPlanTestHistory> = [
  { title: '轮次', dataIndex: 'iteration', key: 'iteration', width: 70, render: (v: number) => `第 ${v + 1} 轮` },
  { title: '任务', dataIndex: 'task_id', key: 'task_id', width: 80, render: (v: number) => `#${v}` },
  {
    title: '任务状态', dataIndex: 'status', key: 'status', width: 100,
    render: (v: string) => {
      const meta = STATUS_META[v] || { label: v, color: 'default' }
      return <Tag color={meta.color}>{meta.label}</Tag>
    },
  },
  { title: '结果条数', dataIndex: 'result_count', key: 'result_count', width: 90, align: 'center' },
  {
    title: '判定', dataIndex: 'passed', key: 'passed', width: 90,
    render: (passed: boolean) => passed
      ? <Tag color="success" icon={<CheckCircleOutlined />}>通过</Tag>
      : <Tag color="error">未通过</Tag>,
  },
  { title: '说明', dataIndex: 'reason', key: 'reason', ellipsis: true },
]

const stepItems = [
  { title: '创建计划' },
  { title: '方案预览与调整' },
  { title: '试采与上线' },
]

export const PlanDetail: React.FC<PlanDetailProps> = ({ flow, canOperate, onOpenLog, onOpenResult }) => {
  const {
    step, plan, editedFlow, creating, actionLoading, customTask,
    createForm, flowForm, history, latestPassed,
    setStep, onCreate, onReplan, onTest, onTestEdited, onApplyFlowEdit, onRegister,
    resetWizard, resultsTaskOf,
  } = flow

  if (!plan && step > 0) return null

  // ---------------- 步骤 0：创建计划 ----------------
  const renderStep0 = () => (
    <Form form={createForm} layout="vertical" style={{ maxWidth: 640 }}>
      <Alert
        type="info" showIcon style={{ marginBottom: 16 }}
        title="粘贴目标页面链接，LLM 将自动规划采集规则（selectors / 翻页 / 详情页 / 过滤）"
        description="页面无法直接访问时可粘贴 HTML 片段，规划将降级使用该片段（离线规划）。"
      />
      <Form.Item
        name="target_url" label="目标页面链接"
        validateTrigger="onBlur"
        rules={[
          { required: true, message: '请输入目标页面链接' },
          { pattern: /^https?:\/\//, message: '必须是 http(s) 地址' },
        ]}
      >
        <Input placeholder="https://example.com/news/list" allowClear />
      </Form.Item>
      <Form.Item
        name="html_snippet" label="HTML 片段（可选）"
        tooltip="可选；预置后规划阶段不再在线抓取，适合需要登录或反爬严格的页面"
      >
        <Input.TextArea rows={6} placeholder="粘贴目标页面的 HTML 片段（最多 200000 字符）" />
      </Form.Item>
      {canOperate && (
        <Button type="primary" icon={<ThunderboltOutlined />} loading={creating} onClick={onCreate}>
          创建并开始规划
        </Button>
      )}
    </Form>
  )

  // ---------------- 步骤 1：方案预览与本地微调 ----------------
  const renderStep1 = () => {
    if (!plan) return null
    const svcFlow = plan.plan_json?.flow || null
    return (
      <div style={{ maxWidth: 860 }}>
        {plan.status === 'planning' && (
          <Alert
            type="info" showIcon style={{ marginBottom: 16 }}
            title={`计划 #${plan.id} 正在通过 LLM 规划采集方案...（每 2.5 秒自动刷新）`}
          />
        )}
        {plan.status === 'failed' && (
          <Alert
            type="error" showIcon style={{ marginBottom: 16 }}
            title="规划失败"
            description={plan.error_message || '未知错误'}
          />
        )}
        {plan.status === 'draft' && !svcFlow && (
          <Alert
            type="warning" showIcon style={{ marginBottom: 16 }}
            title="方案尚未生成"
            description="该计划还没有规划产物，可点击「重新规划」触发 LLM 规划。"
          />
        )}
        {svcFlow && <FlowPreview flow={svcFlow} />}
        {svcFlow && canOperate && (
          <Collapse
            size="small"
            style={{ marginBottom: 16 }}
            items={[{
              key: 'edit',
              label: '微调方案（本地预览，可直跑验证）',
              children: (
                <Form form={flowForm} layout="vertical">
                  <Form.Item label="列表页提取规则" required tooltip="字段名 + 选择器类型（xpath/css/regex）+ 表达式">
                    <SelectorRowList name="selectors" />
                  </Form.Item>
                  <Form.Item label="分页设置">
                    <Collapse size="small" items={[{
                      key: 'pagination',
                      label: '自动翻页（留空选择器表示不翻页）',
                      children: (
                        <>
                          <Form.Item name={['pagination', 'selector']} label="下一页选择器" style={{ marginBottom: 8 }}>
                            <Input placeholder="如 a.next" />
                          </Form.Item>
                          <Form.Item name={['pagination', 'type']} label="选择器类型" style={{ marginBottom: 8 }}>
                            <Select options={[
                              { value: 'css', label: 'CSS' },
                              { value: 'xpath', label: 'XPath' },
                            ]} />
                          </Form.Item>
                          <Form.Item name={['pagination', 'max_pages']} label="最大页数" style={{ marginBottom: 0 }}>
                            <InputNumber min={1} max={100} />
                          </Form.Item>
                        </>
                      ),
                    }]} />
                  </Form.Item>
                  <Form.Item label="详情页设置">
                    <Collapse size="small" items={[{
                      key: 'detail',
                      label: '详情页二次采集（两项都填才生效）',
                      children: (
                        <>
                          <Form.Item name={['detail', 'list_selector']} label="列表项选择器（css）" style={{ marginBottom: 8 }}>
                            <Input placeholder="如 li.news" />
                          </Form.Item>
                          <Form.Item name={['detail', 'url_selector']} label="链接选择器（xpath）" style={{ marginBottom: 8 }}>
                            <Input placeholder="如 .//a/@href" />
                          </Form.Item>
                          <Form.Item label="详情页提取规则" style={{ marginBottom: 0 }}>
                            <SelectorRowList name="detail_selectors" addLabel="添加详情字段规则" />
                          </Form.Item>
                        </>
                      ),
                    }]} />
                  </Form.Item>
                  <Form.Item label="条件过滤">
                    <FilterRuleList />
                  </Form.Item>
                  <Button icon={<CheckCircleOutlined />} onClick={onApplyFlowEdit}>应用调整</Button>
                </Form>
              ),
            }]} />
        )}
        {canOperate && (
          <Space wrap>
            <Button
              icon={<ReloadOutlined />} loading={actionLoading === 'plan'}
              disabled={plan.status === 'planning'}
              onClick={onReplan}
            >
              重新规划
            </Button>
            {svcFlow && (
              <Button
                type="primary" icon={<ExperimentOutlined />}
                loading={actionLoading === 'test'}
                disabled={plan.status === 'planning'}
                onClick={onTest}
              >
                试采（服务端方案）
              </Button>
            )}
            {svcFlow && editedFlow && (
              <Button
                icon={<ThunderboltOutlined />} loading={actionLoading === 'test_edited'}
                disabled={plan.status === 'planning'}
                onClick={onTestEdited}
              >
                试采调整后方案
              </Button>
            )}
          </Space>
        )}
      </div>
    )
  }

  // ---------------- 步骤 2：试采历史与上线 ----------------
  const renderStep2 = () => {
    if (!plan) return null
    const testing = plan.status === 'testing'
    return (
      <div style={{ maxWidth: 860 }}>
        {plan.status === 'registered' && (
          <Alert
            type="success" showIcon style={{ marginBottom: 16 }}
            title={`已上线为爬虫定义：${plan.plan_json?.registered_definition || '-'}`}
            description="可在「爬虫管理 → 任务列表」中选择该 flow 类型爬虫发起正式采集。"
          />
        )}
        {testing && latestPassed && (
          <Alert
            type="success" showIcon style={{ marginBottom: 16 }}
            title="最近一次试采通过，可一键上线注册为 flow 类型爬虫定义"
          />
        )}
        {testing && !latestPassed && (
          <Alert
            type="info" showIcon style={{ marginBottom: 16 }}
            title={`试采进行中（第 ${(plan.iteration_count || 0) + 1} 轮，失败将自动修复迭代）...每 2.5 秒自动刷新`}
          />
        )}
        {plan.status === 'failed' && (
          <Alert
            type="error" showIcon style={{ marginBottom: 16 }}
            title="试采未通过（自动修复迭代已达上限）"
            description={plan.error_message || '可回到方案预览调整后重试'}
          />
        )}
        {history.length > 0 ? (
          <>
            <Text type="secondary" style={{ display: 'block', marginBottom: 6 }}>试采历史（各轮结果对比）</Text>
            <Table
              size="small"
              dataSource={history}
              rowKey={(record) => `${record.iteration}-${record.task_id}`}
              pagination={false}
              columns={historyColumns}
              style={{ marginBottom: 16 }}
            />
          </>
        ) : (
          <Empty description="暂无试采记录（试采启动后展示各轮结果）" style={{ marginBottom: 16 }} />
        )}
        {canOperate && (
          <Space wrap>
            <Button
              type="primary" icon={<RocketOutlined />}
              loading={actionLoading === 'register'}
              disabled={!latestPassed || plan.status === 'planning' || plan.status === 'registered'}
              onClick={onRegister}
            >
              一键上线注册
            </Button>
            <Button
              icon={<ExperimentOutlined />} loading={actionLoading === 'test'}
              disabled={plan.status === 'planning' || plan.status === 'registered'}
              onClick={onTest}
            >
              重新试采
            </Button>
            <Button icon={<EditOutlined />} onClick={() => setStep(1)}>返回方案预览</Button>
          </Space>
        )}
        {plan.test_task_id && (
          <div style={{ marginTop: 12 }}>
            <Text type="secondary" style={{ marginRight: 8 }}>
              最近试采任务 #{plan.test_task_id}：
            </Text>
            <Space>
              <Button
                type="link" size="small" icon={<FileTextOutlined />}
                onClick={() => onOpenLog(plan.test_task_id!, 'running')}
              >
                查看日志
              </Button>
              <Button
                type="link" size="small" icon={<EyeOutlined />}
                onClick={() => {
                  const rt = resultsTaskOf(plan) as Task
                  onOpenResult(rt.id, rt.status, rt.result_count)
                }}
              >
                查看结果
              </Button>
            </Space>
          </div>
        )}
        {customTask && (
          <div style={{ marginTop: 8 }}>
            <Space>
              <Text type="secondary">调整方案试采任务 #{customTask.id}：</Text>
              <Tag color={STATUS_META[customTask.status]?.color || 'default'}>
                {STATUS_META[customTask.status]?.label || customTask.status}
              </Tag>
              <Button
                type="link" size="small" icon={<FileTextOutlined />}
                onClick={() => onOpenLog(customTask.id, customTask.status)}
              >
                查看日志
              </Button>
              <Button
                type="link" size="small" icon={<EyeOutlined />}
                onClick={() => onOpenResult(customTask.id, customTask.status)}
              >
                查看结果
              </Button>
            </Space>
          </div>
        )}
      </div>
    )
  }

  return (
    <>
      <Steps current={step} items={stepItems} style={{ marginBottom: 24, maxWidth: 860 }} />
      {step > 0 && plan && (
        <div style={{ marginBottom: 16 }}>
          <Space wrap>
            <Tag color="blue">计划 #{plan.id}</Tag>
            <Text type="secondary" style={{ maxWidth: 480 }} ellipsis>{plan.target_url}</Text>
            <Tag color={(AI_PLAN_STATUS_META[plan.status] || { color: 'default' }).color}>
              {(AI_PLAN_STATUS_META[plan.status] || { label: plan.status }).label}
            </Tag>
            <Button type="link" size="small" onClick={resetWizard}>重置向导</Button>
          </Space>
        </div>
      )}
      {step === 0 && renderStep0()}
      {step === 1 && renderStep1()}
      {step === 2 && renderStep2()}
    </>
  )
}

export default PlanDetail
