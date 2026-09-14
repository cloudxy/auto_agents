/**
 * T-37（FR-101）：专家团成员域扩 expert∪agent（组件面）。
 * GWT-101.1/101.2 混合成员提交（typed payload）；GWT-101.3 成员可选域两类、组长仅专家；
 * GWT-101.4 无 agent 资产 → 空态句且仍可纯专家组建；详情成员行类型标注；
 * 页面无「执行/运行」措辞（一期无执行态）。
 */
import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import type { AssetRow } from '../../services/capabilities'

const perm = {
  hasPermission: () => true,
  isPlatformAdmin: true,
  role: 'admin',
  isAdmin: false,
  permissions: [] as string[],
  filteredMenus: [] as unknown[],
}

jest.mock('../../services/capabilities', () => ({
  listAssets: jest.fn(),
  createTeam: jest.fn(),
  getTeamDetail: jest.fn(),
}))

jest.mock('../../hooks/usePermission', () => ({
  usePermission: () => perm,
}))

import TeamLeafTab from './TeamLeafTab'
import { createTeam, getTeamDetail, listAssets } from '../../services/capabilities'

const list = listAssets as jest.Mock
const create = createTeam as jest.Mock
const detail = getTeamDetail as jest.Mock

const row = (over: Partial<AssetRow> = {}): AssetRow => ({
  id: 1,
  asset_type: 'team',
  name: 'review-team',
  title: '评审专家团',
  category: 'team',
  status: 'experimental',
  sync_state: 'ok',
  listing_state: 'listed',
  listed_at: '2026-01-01T00:00:00',
  source_type: 'self_built',
  ...over,
})

function stubList(expertNames: string[], agentNames: string[], teams: AssetRow[] = [row()]) {
  list.mockImplementation((type?: string) => {
    if (type === 'expert') {
      return Promise.resolve({ total: expertNames.length, items: expertNames.map((n, i) => row({ id: 100 + i, asset_type: 'expert', name: n, title: n })) })
    }
    if (type === 'agent') {
      return Promise.resolve({ total: agentNames.length, items: agentNames.map((n, i) => row({ id: 200 + i, asset_type: 'agent', name: n, title: n })) })
    }
    if (type === 'team') {
      return Promise.resolve({ total: teams.length, items: teams })
    }
    return Promise.resolve({ total: 0, items: [] })
  })
}

const openCreateModal = async () => {
  fireEvent.click(screen.getByRole('button', { name: '组建专家团' }))
  await screen.findByText('团长（专家）')
}

/** antd v6：Select 无 .ant-select-selector，mousedown 目标是 .ant-select 根；弹窗内两把选择器 */
const openModalSelect = (idx: number) => {
  const modal = document.querySelector('.ant-modal') as HTMLElement
  const selects = modal.querySelectorAll('.ant-select')
  fireEvent.mouseDown(selects[idx])
}

const optionTexts = (): string[] =>
  Array.from(document.querySelectorAll('.ant-select-item-option-content')).map(
    (e) => e.textContent || '',
  )

/** antd v6：分组下拉 role=option 不可靠（jsdom 只暴露部分），按内容类名定位点击 */
const clickDropdownOption = async (text: string) => {
  const node = await waitFor(() => {
    const hit = Array.from(document.querySelectorAll('.ant-select-item-option-content'))
      .find((e) => (e.textContent || '').trim() === text)
    if (!hit) throw new Error(`option not found: ${text}`)
    return hit
  })
  fireEvent.click(node.closest('.ant-select-item-option') as HTMLElement)
}

const fillAndSubmit = async (memberLabels: string[]) => {
  fireEvent.change(screen.getByLabelText('团队名'), { target: { value: 'mixed-team' } })
  openModalSelect(0) // 团长
  await clickDropdownOption('code-reviewer')
  openModalSelect(1) // 成员
  for (const label of memberLabels) {
    await clickDropdownOption(label)
  }
  // antd 两字中文按钮自动插空格（创建 → 创 建）
  fireEvent.click(screen.getByRole('button', { name: /创\s*建/ }))
}

beforeEach(() => {
  create.mockReset()
  detail.mockReset()
  create.mockResolvedValue(undefined)
})

test('GWT-101.3: member domain is expert∪agent, leader stays expert-only', async () => {
  stubList(['code-reviewer'], ['researcher'])
  render(<TeamLeafTab onSubscribe={jest.fn()} />)
  await openCreateModal()

  // 团长下拉：仅专家
  openModalSelect(0)
  await waitFor(() => expect(optionTexts()).toContain('code-reviewer'))
  expect(optionTexts().join()).not.toContain('researcher')

  // 成员下拉：专家 ∪ 智能体，选项带类型标签
  openModalSelect(1)
  await waitFor(() => expect(optionTexts()).toContain('code-reviewer（专家）'))
  expect(optionTexts()).toContain('researcher（智能体）')
})

test('GWT-101.1/101.2: mixed members submit as typed payload', async () => {
  stubList(['code-reviewer'], ['researcher'])
  render(<TeamLeafTab onSubscribe={jest.fn()} />)
  await openCreateModal()

  await fillAndSubmit(['code-reviewer（专家）', 'researcher（智能体）'])

  await waitFor(() => expect(create).toHaveBeenCalledTimes(1))
  expect(create).toHaveBeenCalledWith({
    name: 'mixed-team',
    leader: 'code-reviewer',
    members: [
      { type: 'expert', name: 'code-reviewer' },
      { type: 'agent', name: 'researcher' },
    ],
    workflow_md: '',
  })
})

test('GWT-101.4: zero agent assets shows empty copy and expert-only team still works', async () => {
  stubList(['code-reviewer'], [])
  render(<TeamLeafTab onSubscribe={jest.fn()} />)
  await openCreateModal()

  expect(await screen.findByText('还没有智能体资产')).toBeInTheDocument()

  await fillAndSubmit(['code-reviewer（专家）'])
  await waitFor(() => expect(create).toHaveBeenCalledTimes(1))
  expect(create).toHaveBeenCalledWith({
    name: 'mixed-team',
    leader: 'code-reviewer',
    members: [{ type: 'expert', name: 'code-reviewer' }],
    workflow_md: '',
  })
})

test('GWT-101.1/101.4: team detail lists members with type tag', async () => {
  stubList(['code-reviewer'], ['researcher'])
  detail.mockResolvedValue({
    name: 'review-team',
    title: '评审专家团',
    status: 'experimental',
    leader: 'code-reviewer',
    members: [
      { type: 'expert', name: 'code-reviewer' },
      { type: 'agent', name: 'researcher' },
      'legacy-expert',
    ],
    workflow_md: '团长拆解 → 成员协同 → 汇总交付',
  })
  render(<TeamLeafTab onSubscribe={jest.fn()} />)

  // antd 两字中文按钮自动插空格（详情 → 详 情）
  fireEvent.click(await screen.findByRole('button', { name: /详\s*情/ }))
  expect(await screen.findByText('智能体 · researcher')).toBeInTheDocument()
  expect(screen.getByText('专家 · code-reviewer')).toBeInTheDocument()
  expect(screen.getByText('专家 · legacy-expert')).toBeInTheDocument()
  expect(detail).toHaveBeenCalledWith('review-team')
})

test('no execution wording on the create-team modal (一期无执行态)', async () => {
  stubList(['code-reviewer'], ['researcher'])
  render(<TeamLeafTab onSubscribe={jest.fn()} />)
  await openCreateModal()

  const text = document.body.textContent || ''
  expect(text).not.toMatch(/执行|运行/)
})
