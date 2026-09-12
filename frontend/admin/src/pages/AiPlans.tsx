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
import React, { useCallback, useState } from 'react'
import { Button, Steps } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import type { AiPlan } from '../services/ai'
import { LogDrawer } from '../components/spider/LogDrawer'
import { ResultDrawer } from '../components/spider/ResultDrawer'
import type { Task, SpiderMap } from '../components/spider/types'
import { usePermission } from '../hooks/usePermission'
import { useAiPlanFlow } from '../hooks/useAiPlanFlow'
import { PlanDetail } from '../components/ai/PlanDetail'
import { PlanList } from '../components/ai/PlanList'
import PageHeaderTabs, { pageTabPaneStyle } from '../components/layout/PageHeaderTabs'

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

/** 页级 tab（§0.10 / T-34：顶栏行 = 页名「AI 采集规划」+ 本两 tab，与欢迎语同一行） */
const PAGE_TAB_ITEMS = [
  { key: 'wizard', label: '采集向导' },
  { key: 'plans', label: '方案列表' },
]

const AiPlans: React.FC = () => {
  const { hasPermission } = usePermission()
  const canOperate = hasPermission('btn:create') // 规划/试采/上线与创建共享 operator 权限
  const canDelete = hasPermission('btn:delete')  // 删除计划仅 admin

  // 向导状态机（状态/轮询/动作全部收敛于 hook）
  const wizard = useAiPlanFlow()

  // 页面组合状态（T-34：两 tab 经 PageHeaderTabs 上提顶栏；pane 首次激活挂载、此后保持）
  const [activeTab, setActiveTab] = useState('wizard')
  const [visitedTabs, setVisitedTabs] = useState<Record<string, boolean>>({ wizard: true })
  const onTabChange = useCallback((key: string) => {
    setActiveTab(key)
    setVisitedTabs((visited) => (visited[key] ? visited : { ...visited, [key]: true }))
  }, [])
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
    <>
      {/* 页级 tab 上提顶栏（T-34 / GWT-99.1）；无槽位（单测直渲染）时原位回退 */}
      <PageHeaderTabs items={PAGE_TAB_ITEMS} activeKey={activeTab} onChange={onTabChange} />

      {/* 原 Card extra 的「新建采集计划」保留为内容区动作行（GWT-99.3 动作等价） */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
        <Button icon={<PlusOutlined />} onClick={() => { wizard.resetWizard(); onTabChange('wizard') }}>
          新建采集计划
        </Button>
      </div>

      {/* 内容区直接当前 tab 开始；pane 首次激活挂载后保持，display 切换 + ≤150ms 透明度 */}
      {visitedTabs.wizard && (
        <div style={pageTabPaneStyle(activeTab === 'wizard')}>
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
        </div>
      )}
      {visitedTabs.plans && (
        <div style={pageTabPaneStyle(activeTab === 'plans')}>
          <PlanList canDelete={canDelete} onOpenPlan={handleOpenPlan} />
        </div>
      )}

      {/* 试采日志抽屉（轮询模式与任务日志一致） */}
      <LogDrawer task={logTask} spiderMap={PSEUDO_SPIDER_MAP} onClose={() => setLogTask(null)} />
      {/* 试采结果抽屉 */}
      <ResultDrawer task={resultTask} spiderMap={PSEUDO_SPIDER_MAP} onClose={() => setResultTask(null)} />
    </>
  )
}

export default AiPlans
