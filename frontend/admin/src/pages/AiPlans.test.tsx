/**
 * T-34 / FR-99（§0.10 页头规范）AI 采集规划页 UI 面：
 * - GWT-99.1 页名「AI 采集规划」唯一标题在顶栏：页内无「AI 采集」标题卡，内容区直接业务内容
 * - GWT-99.3 两 tab（采集向导/方案列表）上提后切换只动内容区、pane 状态不丢；
 *   「新建采集计划」动作保留在内容区（重置向导并切回向导 tab）
 *
 * mock 边界：向导状态机（useAiPlanFlow）与 PlanDetail/PlanList/抽屉组件——
 * 本套只钉页头结构与 tab 机制，数据面沿用各组件自测。
 */
import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'

jest.mock('../hooks/usePermission', () => ({
  usePermission: () => ({
    hasPermission: () => true,
    isAdmin: true,
    role: 'admin',
    permissions: [],
    permissionsReady: true,
    filteredMenus: [],
  }),
}))

const mockResetWizard = jest.fn()

jest.mock('../hooks/useAiPlanFlow', () => ({
  useAiPlanFlow: () => ({ step: 0, resetWizard: mockResetWizard }),
}))

jest.mock('../components/ai/PlanDetail', () => ({
  PlanDetail: () => <div data-testid="wizard-pane">向导内容</div>,
}))
jest.mock('../components/ai/PlanList', () => ({
  PlanList: () => <div data-testid="plans-pane">方案列表内容</div>,
}))
jest.mock('../components/spider/LogDrawer', () => ({ LogDrawer: () => null }))
jest.mock('../components/spider/ResultDrawer', () => ({ ResultDrawer: () => null }))

import AiPlans from './AiPlans'

test('页头规范：无「AI 采集」标题卡，内容区直接向导；tab 上提可用（GWT-99.1）', () => {
  render(<AiPlans />)
  // 页名唯一标题在顶栏：页内不复述（原 Card title「AI 采集」不在场）
  expect(screen.queryByText('AI 采集')).toBeNull()
  expect(screen.queryByRole('heading')).toBeNull()
  // 两 tab 在场（无 AdminLayout 槽位时 PageHeaderTabs 原位回退）
  expect(screen.getByRole('tab', { name: /采集向导/ })).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: /方案列表/ })).toBeInTheDocument()
  // 内容区第一屏即业务内容（Steps + 向导）+ 动作保留（GWT-99.3）
  expect(screen.getByTestId('wizard-pane')).toBeVisible()
  expect(screen.getByText('输入目标')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /新建采集计划/ })).toBeInTheDocument()
})

test('tab 切换只动内容区；切回向导 pane 状态不丢；新建动作重置并回到向导（GWT-99.3）', () => {
  render(<AiPlans />)
  fireEvent.click(screen.getByRole('tab', { name: /方案列表/ }))
  expect(screen.getByTestId('plans-pane')).toBeVisible()
  expect(screen.getByTestId('wizard-pane')).not.toBeVisible()
  // 切回：向导 pane 仍是既有实例（常挂载，display 切换）
  fireEvent.click(screen.getByRole('tab', { name: /采集向导/ }))
  expect(screen.getByTestId('wizard-pane')).toBeVisible()
  expect(screen.getByTestId('plans-pane')).not.toBeVisible()
  // 在方案列表 tab 点「新建采集计划」：重置向导 + 切回向导 tab
  fireEvent.click(screen.getByRole('tab', { name: /方案列表/ }))
  fireEvent.click(screen.getByRole('button', { name: /新建采集计划/ }))
  expect(mockResetWizard).toHaveBeenCalled()
  expect(screen.getByTestId('wizard-pane')).toBeVisible()
})
