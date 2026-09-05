/**
 * AI 采集页面 - 三步向导（创建规划 → 方案预览 → 试采上线）+ 方案列表
 *
 * 期 4 前端治理拆分（原 849 行页面文件 → 组合层）：
 * - hooks/useAiPlanFlow.ts        向导状态机（step/plan/轮询/动作）
 * - components/ai/PlanForm.tsx    方案展示与编辑（SelectorTable/FlowPreview/FilterRuleList）
 * - components/ai/PlanDetail.tsx  向导步骤渲染（三步内容 + 试采历史）
 * - components/ai/PlanList.tsx    方案列表（自含分页/筛选/删除）
 * 本文件仅保留组合职责：Tabs 编排、权限注入、日志/结果抽屉。
 */
import React, { useState } from 'react'
import { Button, Card, Steps, Tabs } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import type { AiPlan } from '../services/ai'
import { LogDrawer } from '../components/spider/LogDrawer'
import { ResultDrawer } from '../components/spider/ResultDrawer'
import type { Task, SpiderMap } from '../components/spider/types'
import { usePermission } from '../hooks/usePermission'
import { useAiPlanFlow } from '../hooks/useAiPlanFlow'
import { PlanDetail } from '../components/ai/PlanDetail'
import { PlanList } from '../components/ai/PlanList'

/** 试采/日志抽屉用的爬虫映射（flow_generic 为流程化引擎） */
const PSEUDO_SPIDER_MAP: SpiderMap = { flow_generic: { title: '流程化采集', type: 'flow' } }

/** 伪 Task（复用 LogDrawer/ResultDrawer：仅依赖 id/spider_name/status） */
const pseudoTask = (taskId: number, status: string, resultCount = 0): Task => ({
  id: taskId,
  spider_name: 'flow_generic',
  status,
  priority: 'low',
  result_count: resultCount,
})

const AiPlans: React.FC = () => {
  const { hasPermission } = usePermission()
  const canOperate = hasPermission('btn:create') // 规划/试采/上线与创建共享 operator 权限
  const canDelete = hasPermission('btn:delete')  // 删除计划仅 admin

  // 向导状态机（状态/轮询/动作全部收敛于 hook）
  const wizard = useAiPlanFlow()

  // 页面组合状态
  const [activeTab, setActiveTab] = useState('wizard')
  const [logTask, setLogTask] = useState<Task | null>(null)
  const [resultTask, setResultTask] = useState<Task | null>(null)

  // 试采抽屉开关联动（伪 Task 复用任务日志/结果组件）
  const openLog = (taskId: number, status: string, resultCount = 0) =>
    setLogTask(pseudoTask(taskId, status, resultCount))
  const openResult = (taskId: number, status: string, resultCount = 0) =>
    setResultTask(pseudoTask(taskId, status, resultCount))

  // 从列表「继续」：载入计划到向导并切回向导 tab
  const handleOpenPlan = (p: AiPlan) => {
    wizard.openPlanInWizard(p)
    setActiveTab('wizard')
  }

  return (
    <Card
      title="AI 采集"
      extra={
        <Button icon={<PlusOutlined />} onClick={() => { wizard.resetWizard(); setActiveTab('wizard') }}>
          新建采集计划
        </Button>
      }
    >
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: 'wizard',
            label: '采集向导',
            children: (
              <>
              {/* UX1（工单 89）：流程阶段指示——输入目标 → 方案与试采 → 上线 */}
              <Steps
                size="small"
                current={wizard.step}
                style={{ marginBottom: 20, maxWidth: 640 }}
                items={[
                  { title: '输入目标' },
                  { title: '方案与试采' },
                  { title: '上线' },
                ]}
              />
              <PlanDetail
                flow={wizard}
                canOperate={canOperate}
                onOpenLog={openLog}
                onOpenResult={openResult}
              />
              </>
            ),
          },
          {
            key: 'plans',
            label: '方案列表',
            children: <PlanList canDelete={canDelete} onOpenPlan={handleOpenPlan} />,
          },
        ]}
      />

      {/* 试采日志抽屉（轮询模式与任务日志一致） */}
      <LogDrawer task={logTask} spiderMap={PSEUDO_SPIDER_MAP} onClose={() => setLogTask(null)} />
      {/* 试采结果抽屉 */}
      <ResultDrawer task={resultTask} spiderMap={PSEUDO_SPIDER_MAP} onClose={() => setResultTask(null)} />
    </Card>
  )
}

export default AiPlans
