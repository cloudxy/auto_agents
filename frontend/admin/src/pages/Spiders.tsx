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
import { Card, Tabs, message } from 'antd'
import { ClockCircleOutlined, AlertOutlined, BookOutlined } from '@ant-design/icons'
import {
  fetchRegistry, fetchTasks, deleteTask, controlTask,
  fetchTemplates,
} from '../services/spiders'
import { usePermission } from '../hooks/usePermission'
import { apiErrorMessage } from '../utils/errorMessage'
import type { SpiderMap, Task, SpiderRegistry, TaskTemplate } from '../components/spider/types'
import type { TaskPreset } from '../components/spider/TaskModal'

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

const PAGE_SIZE = 20

const Spiders: React.FC = () => {
  // 角色权限（后端为最终防线，前端仅隐藏高危按钮）
  const { hasPermission, isAdmin } = usePermission()
  const canCreate = hasPermission('btn:create')
  const canDelete = hasPermission('btn:delete')
  const canSchedule = hasPermission('btn:schedule')
  const canOperate = hasPermission('btn:create') // 暂停/终止与创建共享 operator 权限

  const [loading, setLoading] = useState(false)
  const [tasks, setTasks] = useState<Task[]>([])
  const [total, setTotal] = useState(0)
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

  const spiderMap = useMemo<SpiderMap>(() => {
    const m: SpiderMap = {}
    registry.spiders.forEach((s: { name: string; title: string; type: string }) => { m[s.name] = { title: s.title, type: s.type } })
    return m
  }, [registry])

  // U1-1：服务端真分页 + 状态/爬虫/优先级筛选（翻到哪页拉哪页，不再只取前 50 条）
  const loadTasks = useCallback(async (showSpin = true, targetPage = page) => {
    if (showSpin) setLoading(true)
    try {
      const res = await fetchTasks((targetPage - 1) * PAGE_SIZE, PAGE_SIZE, {
        priority: priorityFilter,
        status: statusFilter,
        spider_name: spiderFilter,
      })
      setTasks(res.items || [])
      setTotal(res.total || 0)
    } catch (error) {
      message.error('获取任务列表失败')
    } finally {
      if (showSpin) setLoading(false)
    }
  }, [page, priorityFilter, statusFilter, spiderFilter])

  // 筛选/翻页变化：只改状态，由 useEffect([loadTasks]) 依赖驱动自动重载
  // （避免闭包旧值；筛选变化时同时回到第 1 页）
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
    fetchRegistry().then(setRegistry).catch(() => message.error('获取爬虫注册表失败'))
    loadTasks()
    loadTemplates()
  }, [loadTasks, loadTemplates])

  // 存在未终态任务时每 3 秒静默刷新（状态/结果数实时推进）
  useEffect(() => {
    const hasActive = tasks.some((t) => t.status === 'pending' || t.status === 'running')
    if (!hasActive) return
    const timer = setInterval(() => loadTasks(false), 3000)
    return () => clearInterval(timer)
  }, [tasks, loadTasks])

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
    <Card title="爬虫管理">
      <Tabs
        items={[
          {
            key: 'tasks',
            label: '任务列表',
            children: (
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
            ),
          },
          {
            key: 'schedules',
            label: (
              <span><ClockCircleOutlined style={{ marginRight: 4 }} />定时任务</span>
            ),
            children: (
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
            ),
          },
          {
            key: 'files',
            label: '爬虫定义',
            children: (
              <FileTab isAdmin={isAdmin} />
            ),
          },
          {
            key: 'alerts',
            label: (
              <span><AlertOutlined style={{ marginRight: 4 }} />告警规则</span>
            ),
            children: (
              <AlertRulesTab
                registry={registry}
                spiderMap={spiderMap}
                isAdmin={isAdmin}
              />
            ),
          },
          {
            key: 'templates',
            label: (
              <span><BookOutlined style={{ marginRight: 4 }} />任务模板</span>
            ),
            children: (
              <TemplateTab
                spiderMap={spiderMap}
                canCreate={canCreate}
                canDelete={canDelete}
                onRunFromTemplate={onRunFromTemplate}
              />
            ),
          },
        ]}
      />

      {/* 新增任务弹窗 */}
      <TaskModal
        visible={modalOpen}
        registry={registry}
        spiderMap={spiderMap}
        templates={templates}
        preset={preset}
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
    </Card>
  )
}

export default Spiders
