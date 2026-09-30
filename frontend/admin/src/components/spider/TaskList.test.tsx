/**
 * 任务操作列（决策 D6）：「暂停」先下线——现有暂停会丢请求、最后显示已完成（BUG-14）；
 * 运行中任务只留「终止」，恢复入口一并撤下。
 */
import React from 'react'
import { render, screen } from '@testing-library/react'
import type { Task } from './types'
import { TaskList, type TaskListProps } from './TaskList'

const running: Task = { id: 7, spider_name: 'generic', status: 'running', priority: 'normal', result_count: 3 }

const noop = () => undefined
const props = (overrides: Partial<TaskListProps> = {}): TaskListProps => ({
  tasks: [running], loading: false, total: 1, page: 1, pageSize: 10, spiderMap: {},
  canCreate: true, canDelete: true, canOperate: true,
  priorityFilter: undefined, onPriorityFilterChange: noop,
  statusFilter: undefined, onStatusFilterChange: noop,
  spiderFilter: undefined, onSpiderFilterChange: noop, spiderOptions: [],
  onPaginationChange: noop, onRun: noop, onCreateNew: noop, onStop: noop, onDelete: noop,
  onSaveTemplate: noop, onViewLog: noop, onViewResult: noop, onEdit: noop, onRefresh: noop,
  ...overrides,
})

test('running task offers terminate but no pause / resume', () => {
  render(<TaskList {...props()} />)
  expect(screen.getByRole('button', { name: /终\s*止/ })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /暂\s*停/ })).toBeNull()
  expect(screen.queryByRole('button', { name: /恢\s*复/ })).toBeNull()
})
