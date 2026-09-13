/**
 * 爬虫任务管理页面
 *
 * 能力（对齐 Crawlab 的核心交互）：
 * - 任务列表：状态实时轮询（运行中/待分发显示转圈），结果数实时增长
 * - 新增任务：按类型（API 接口 / Web 网页）选择爬虫，参数表单由注册表动态渲染
 * - 运行过程：日志抽屉轮询展示 Worker 运行日志（按任务隔离）
 * - 采集结果：结果抽屉预览 + CSV/JSON 导出
 * - 删除任务：二次确认 + 级联删除采集结果（运行中禁止删除）
 * - 定时任务：Cron 调度计划管理（创建/启停/删除）
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Alert, Button, message } from 'antd'
import { ClockCircleOutlined, AlertOutlined, BookOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import {
  fetchRegistry, fetchTasks, deleteTask, controlTask,
  fetchTemplates,
} from '../services/spiders'
import { fetchNodesPage } from '../services/admin'
import { usePermission } from '../hooks/usePermission'
import { apiErrorMessage } from '../utils/errorMessage'
import type { SpiderMap, Task, SpiderRegistry, TaskTemplate } from '../components/spider/types'
import type { TaskPreset } from '../components/spider/TaskModal'
import { SPIDER_WORKER_OFFLINE_COPY, GO_NODES_TEXT } from '../components/spider/copy'
import PageHeaderTabs, { pageTabPaneStyle } from '../components/layout/PageHeaderTabs'

import { TaskList } from '../components/spider/TaskList'
import { TaskModal } from '../components/spider/TaskModal'
import { LogDrawer } from '../components/spider/LogDrawer'
import { ResultDrawer } from '../components/spider/ResultDrawer'
import { ScheduleTab } from '../components/spider/ScheduleTab'
import { FileTab } from '../components/spider/FileTab'
import { AlertRulesTab } from '../components/spider/AlertRulesTab'
import { TemplateTab } from '../components/spider/TemplateTab'
import { TemplateModal } from '../components/spider/TemplateModal'
import { TaskEditModal } from '../components/spider/TaskEditModal'
import { useQuery } from '@tanstack/react-query'

const PAGE_SIZE = 20

/** 页级 tab（§0.10 / T-34：顶栏行 = 页名「采集任务」+ 本五 tab，与欢迎语同一行） */
const PAGE_TAB_ITEMS = [
  { key: 'tasks', label: '任务列表' },
  {
    key: 'schedules',
    label: <span><ClockCircleOutlined style={{ marginRight: 4 }} />定时任务</span>,
  },
  { key: 'files', label: '采集方案' },
  {
    key: 'alerts',
    label: <span><AlertOutlined style={{ marginRight: 4 }} />告警规则</span>,
  },
  {
    key: 'templates',
    label: <span><BookOutlined style={{ marginRight: 4 }} />任务模板</span>,
  },
]

const Spiders: React.FC = () => {
  // 角色权限（后端为最终防线，前端仅隐藏高危按钮）
  const { hasPermission, isAdmin } = usePermission()
  const navigate = useNavigate()
  const canCreate = hasPermission('btn:create')
  const canDelete = hasPermission('btn:delete')
  const canSchedule = hasPermission('btn:schedule')
  const canOperate = hasPermission('btn:create') // 暂停/终止与创建共享 operator 权限

  const [page, setPage] = useState(1)
  const [priorityFilter, setPriorityFilter] = useState<string | undefined>(undefined)
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined)
  const [spiderFilter, setSpiderFilter] = useState<string | undefined>(undefined)
  const [registry, setRegistry] = useState<SpiderRegistry>({ types: [], spiders: [] })

  // 新增任务弹窗（preset 携带待回填参数）
  const [modalOpen, setModalOpen] = useState(false)
  const [preset, setPreset] = useState<TaskPreset | null>(null)

  // 运行日志抽屉
  const [logTask, setLogTask] = useState<Task | null>(null)

  // 结果抽屉
  const [resultTask, setResultTask] = useState<Task | null>(null)

  // 收藏模板弹窗
  const [templateModalOpen, setTemplateModalOpen] = useState(false)
  const [templateTask, setTemplateTask] = useState<Task | null>(null)

  // 编辑待执行任务弹窗
  const [editTask, setEditTask] = useState<Task | null>(null)

  // 模板列表（供 TaskModal 的"从模板创建"使用）
  const [templates, setTemplates] = useState<TaskTemplate[]>([])

  // 页级 tab（T-34 / GWT-99.1）：五 tab 经 PageHeaderTabs 上提顶栏行；
  // pane 与原 Tabs 同语义——首次激活才挂载（数据装配时机不变），此后保持（筛选/分页态不丢）
  const [activeTab, setActiveTab] = useState('tasks')
  const [visitedTabs, setVisitedTabs] = useState<Record<string, boolean>>({ tasks: true })
  const onTabChange = useCallback((key: string) => {
    setActiveTab(key)
    setVisitedTabs((visited) => (visited[key] ? visited : { ...visited, [key]: true }))
  }, [])

  const spiderMap = useMemo<SpiderMap>(() => {
    const m: SpiderMap = {}
    registry.spiders.forEach((s: { name: string; title: string; type: string }) => { m[s.name] = { title: s.title, type: s.type } })
    return m
  }, [registry])

  // 工单 78：任务列表交 react-query（U1-1 服务端真分页；存在未终态任务时 3s 轮询）
  const { data: nodesRes, isFetched: nodesFetched } = useQuery({
    queryKey: ['spider-nodes'],
    queryFn: () => fetchNodesPage<{ worker_id: string }>(),
    refetchInterval: 15000,
  })
  const workerOffline = nodesFetched && (nodesRes?.total ?? 0) === 0

  const { data: tasksRes, isLoading: loading, refetch: refetchTasks } = useQuery({
    queryKey: ['spider-tasks', page, priorityFilter, statusFilter, spiderFilter],
    queryFn: () => fetchTasks((page - 1) * PAGE_SIZE, PAGE_SIZE, {
      priority: priorityFilter,
      status: statusFilter,
      spider_name: spiderFilter,
    }),
    refetchInterval: (query) => {
      const active = (query.state.data?.items || []).some(
        (t) => t.status === 'pending' || t.status === 'running')
      return active ? 3000 : false
    },
  })
  const tasks = tasksRes?.items || []
  const total = tasksRes?.total || 0
  // 工单 78 后任务列表归 react-query：挂载自动首拉，筛选/翻页经 queryKey 变化自动重取，
  // loadTasks 仅作手动刷新入口（禁止进 useEffect 依赖——非 memoized 引用每渲染必变，会引发无限刷接口）
  const loadTasks = async (_showSpin = true, _targetPage?: number) => { await refetchTasks() }

  // 筛选/翻页变化：只改状态（筛选变化时同时回到第 1 页）
  const changePriorityFilter = (v: string | undefined) => { setPriorityFilter(v); setPage(1) }
  const changeStatusFilter = (v: string | undefined) => { setStatusFilter(v); setPage(1) }
  const changeSpiderFilter = (v: string | undefined) => { setSpiderFilter(v); setPage(1) }
  const changePagination = (p: number) => { setPage(p) }

  const loadTemplates = useCallback(async () => {
    try {
      const res = await fetchTemplates()
      setTemplates(res || [])
    } catch (error) {
      message.error('获取任务模板失败')
    }
  }, [])

  useEffect(() => {
    fetchRegistry().then(setRegistry).catch((e) => message.error(apiErrorMessage(e, '获取爬虫注册表失败')))
    loadTemplates()
  }, [loadTemplates])


  // ---------------- 新增任务弹窗 ----------------
  const openModal = (presetArg?: TaskPreset | null) => {
    setPreset(presetArg || null)
    setModalOpen(true)
  }

  const onTaskSubmitSuccess = (task: Task) => {
    loadTasks(false)
    loadTemplates()
    // 直接打开日志抽屉，观察运行过程
    setLogTask(task)
  }

  // ---------------- 删除 ----------------
  const onDelete = async (task: Task) => {
    try {
      const res = await deleteTask(task.id)
      message.success(`任务 #${res.task_id} 已删除（级联清理 ${res.removed_results} 条结果）`)
      loadTasks(false)
    } catch (error) {
      message.error(apiErrorMessage(error, '删除失败'))
    }
  }

  // ---------------- 任务控制（A4）：暂停/恢复/终止 ----------------
  const onControlTask = async (task: Task, action: 'pause' | 'resume' | 'stop') => {
    const actionLabels: Record<string, string> = { pause: '暂停', resume: '恢复', stop: '终止' }
    try {
      const res = await controlTask(task.id, action)
      message.success(res.message || `任务 #${task.id} 已${actionLabels[action]}`)
      await loadTasks(false)
    } catch (error) {
      message.error(apiErrorMessage(error, `${actionLabels[action]}失败`))
    }
  }

  // ---------------- 收藏模板 ----------------
  const openTemplateModal = (task: Task) => {
    setTemplateTask(task)
    setTemplateModalOpen(true)
  }

  const onTemplateSubmitSuccess = () => {
    loadTemplates()
  }

  // ---------------- 从模板运行 ----------------
  const onRunFromTemplate = (task: Task) => {
    loadTasks(false)
    setLogTask(task)
  }

  return (
    <>
      {/* 页级 tab 上提顶栏（T-34 / GWT-99.1）；无槽位（单测直渲染）时原位回退 */}
      <PageHeaderTabs items={PAGE_TAB_ITEMS} activeKey={activeTab} onChange={onTabChange} />

      {/* 无工人提示（FR-85 条件态，§0.10 允许保留；非装饰横幅）+「去节点」下一步（T-18 / GWT-85.1） */}
      {workerOffline && (
        <Alert
          type="warning"
          showIcon
          title={SPIDER_WORKER_OFFLINE_COPY}
          action={(
            <Button size="small" onClick={() => navigate('/spiders/nodes')}>
              {GO_NODES_TEXT}
            </Button>
          )}
          style={{ marginBottom: 12 }}
        />
      )}

      {/* 内容区直接当前 tab 开始；pane 首次激活挂载后保持，display 切换 + ≤150ms 透明度 */}
      {visitedTabs.tasks && (
        <div style={pageTabPaneStyle(activeTab === 'tasks')}>
          <TaskList
            tasks={tasks}
            loading={loading}
            total={total}
            page={page}
            pageSize={PAGE_SIZE}
            spiderMap={spiderMap}
            canCreate={canCreate}
            canDelete={canDelete}
            canOperate={canOperate}
            priorityFilter={priorityFilter}
            onPriorityFilterChange={changePriorityFilter}
            statusFilter={statusFilter}
            onStatusFilterChange={changeStatusFilter}
            spiderFilter={spiderFilter}
            onSpiderFilterChange={changeSpiderFilter}
            spiderOptions={registry.spiders.map((s: { name: string; title: string }) => ({
              value: s.name,
              label: s.title,
            }))}
            onPaginationChange={changePagination}
            onRun={(task: Task) => openModal({ spiderName: task.spider_name, params: task.params, priority: task.priority })}
            onCreateNew={() => openModal()}
            onPause={(task: Task) => onControlTask(task, 'pause')}
            onResume={(task: Task) => onControlTask(task, 'resume')}
            onStop={(task: Task) => onControlTask(task, 'stop')}
            onDelete={onDelete}
            onSaveTemplate={openTemplateModal}
            onViewLog={(task: Task) => setLogTask(task)}
            onViewResult={(task: Task) => setResultTask(task)}
            onEdit={(task: Task) => setEditTask(task)}
            onRefresh={() => loadTasks()}
          />
        </div>
      )}
      {visitedTabs.schedules && (
        <div style={pageTabPaneStyle(activeTab === 'schedules')}>
          <ScheduleTab
            registry={registry}
            spiderMap={spiderMap}
            canCreate={canCreate}
            canSchedule={canSchedule}
            onRunTask={(record) => openModal({
              spiderName: record.spider_name,
              params: record.params,
              priority: undefined,
            })}
          />
        </div>
      )}
      {visitedTabs.files && (
        <div style={pageTabPaneStyle(activeTab === 'files')}>
          <FileTab isAdmin={isAdmin} />
        </div>
      )}
      {visitedTabs.alerts && (
        <div style={pageTabPaneStyle(activeTab === 'alerts')}>
          <AlertRulesTab
            registry={registry}
            spiderMap={spiderMap}
            isAdmin={isAdmin}
          />
        </div>
      )}
      {visitedTabs.templates && (
        <div style={pageTabPaneStyle(activeTab === 'templates')}>
          <TemplateTab
            spiderMap={spiderMap}
            canCreate={canCreate}
            canDelete={canDelete}
            onRunFromTemplate={onRunFromTemplate}
          />
        </div>
      )}

      {/* 新增任务弹窗（workerOffline：0 工人时提交被拦，T-18 / GWT-85.2） */}
      <TaskModal
        visible={modalOpen}
        registry={registry}
        spiderMap={spiderMap}
        templates={templates}
        preset={preset}
        workerOffline={workerOffline}
        onSubmitSuccess={onTaskSubmitSuccess}
        onCancel={() => setModalOpen(false)}
      />

      {/* 运行日志抽屉 */}
      <LogDrawer
        task={logTask}
        spiderMap={spiderMap}
        onClose={() => setLogTask(null)}
      />

      {/* 采集结果抽屉 */}
      <ResultDrawer
        task={resultTask}
        spiderMap={spiderMap}
        onClose={() => setResultTask(null)}
      />

      {/* 收藏为模板弹窗 */}
      <TemplateModal
        visible={templateModalOpen}
        task={templateTask}
        spiderMap={spiderMap}
        onSubmitSuccess={onTemplateSubmitSuccess}
        onCancel={() => setTemplateModalOpen(false)}
      />

      {/* 编辑待执行任务弹窗（仅 pending 可改 params/priority，复用动态表单） */}
      <TaskEditModal
        visible={!!editTask}
        task={editTask}
        registry={registry}
        onSubmitSuccess={() => loadTasks(false)}
        onCancel={() => setEditTask(null)}
      />
    </>
  )
}

export default Spiders
