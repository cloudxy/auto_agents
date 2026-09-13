/**
 * T-40 / FR-103 UI：定义编辑弹窗参数区三形态（api 入口地址+headers / flow 动态键 / 代码型锁定句）、
 * 删除被引用拒绝句原样展示（含 #任务号）、非经办（viewer）无编辑/删除按钮。
 */
import React from 'react'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { FileTab } from './FileTab'

jest.mock('../../services/spiders', () => ({
  fetchSpiderFiles: jest.fn(),
  fetchRegistry: jest.fn(),
  updateDefinition: jest.fn(),
  createDefinition: jest.fn(),
  updateDefinitionMeta: jest.fn(),
  deleteDefinition: jest.fn(),
}))

// babel-jest 工厂引用 mock* 前缀变量（render 时才读取，无 TDZ）
const mockUserState: { current: Record<string, unknown> | null } = { current: null }

jest.mock('../../store/useAuthStore', () => ({
  useAuthStore: (sel: (s: { user: Record<string, unknown> | null }) => unknown) =>
    sel({ user: mockUserState.current }),
}))

// jest.mock 提升后此 import 才能拿到 mock 实现（仓库既有测试同型；import/first 例外）
// eslint-disable-next-line import/first
import {
  fetchSpiderFiles, fetchRegistry, updateDefinitionMeta, deleteDefinition,
} from '../../services/spiders'

const OPERATOR = { tenant_id: 1, tenant_role: 'operator', is_platform_admin: false }
const VIEWER = { tenant_id: 1, tenant_role: 'viewer', is_platform_admin: false }

const FILES = {
  items: [
    { name: 'news_api', file: 'scrapy/spiders/news_api.py', size_bytes: 2048, registered: true, title: null, enabled: true },
  ],
}
const REGISTRY = {
  types: [],
  spiders: [
    {
      name: 'news_api', title: '资讯 API', type: 'api', description: '接口采集',
      params: { urls: ['https://a.example/feed', 'https://b.example/feed'], headers: { Authorization: 'Bearer tok' } },
    },
    {
      name: 'flow_news', title: 'AI 流程采集', type: 'flow', description: null,
      params: { keyword: '汽车', max_pages: '3' },
    },
    { name: 'web_page', title: '网页采集', type: 'web', description: null },
  ],
}

// 独立渲染无页面级 ConfigProvider（autoInsertSpace），两字按钮按「X X」形态断言
const EDIT_BTN = /编\s*辑/
const DELETE_BTN = /删\s*除/
const SAVE_OK = /^保\s*存$/
const SAVED_TOAST = '已保存。后续新任务将使用新定义。'

function renderTab() {
  // FileTab 空态次链用 useNavigate（GWT-103.4）→ 需 Router 上下文（TaskModal.test 同型）
  return render(
    <MemoryRouter>
      <FileTab isAdmin />
    </MemoryRouter>,
  )
}

/** 定位表格行（次行 name 文本）→ 点行内编辑 → 等弹窗标题 */
async function openEdit(name: string) {
  // eslint-disable-next-line testing-library/no-node-access -- antd Table 行定位（仓库既有手法）
  const row = (await screen.findByText(name)).closest('tr')
  expect(row).not.toBeNull()
  fireEvent.click(within(row as HTMLElement).getByRole('button', { name: EDIT_BTN }))
  expect(await screen.findByText(`编辑定义元信息：${name}`)).toBeInTheDocument()
}

beforeEach(() => {
  jest.clearAllMocks()
  mockUserState.current = OPERATOR
  ;(fetchSpiderFiles as jest.Mock).mockResolvedValue(FILES)
  ;(fetchRegistry as jest.Mock).mockResolvedValue(REGISTRY)
  ;(updateDefinitionMeta as jest.Mock).mockResolvedValue({ ...REGISTRY.spiders[0], enabled: true })
})

test('api 型：入口地址多行 + headers 键值回显；保存提交 params={urls,headers} 并提示新任务句', async () => {
  renderTab()
  await openEdit('news_api')
  expect((screen.getByLabelText('入口地址') as HTMLTextAreaElement).value)
    .toBe('https://a.example/feed\nhttps://b.example/feed')
  expect(screen.getByDisplayValue('Authorization')).toBeInTheDocument()
  expect(screen.getByDisplayValue('Bearer tok')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: SAVE_OK }))
  expect(await screen.findByText(SAVED_TOAST)).toBeInTheDocument()
  expect(updateDefinitionMeta).toHaveBeenCalledWith('news_api', {
    title: '资讯 API',
    description: '接口采集',
    params: {
      urls: ['https://a.example/feed', 'https://b.example/feed'],
      headers: { Authorization: 'Bearer tok' },
    },
  })
})

test('flow 型：按 params 键动态文本输入；保存提交动态键值', async () => {
  renderTab()
  await openEdit('flow_news')
  expect((screen.getByLabelText('keyword') as HTMLInputElement).value).toBe('汽车')
  expect((screen.getByLabelText('max_pages') as HTMLInputElement).value).toBe('3')
  expect(screen.queryByLabelText('入口地址')).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('keyword'), { target: { value: '新能源' } })
  fireEvent.click(screen.getByRole('button', { name: SAVE_OK }))
  expect(await screen.findByText(SAVED_TOAST)).toBeInTheDocument()
  expect(updateDefinitionMeta).toHaveBeenCalledWith('flow_news', {
    title: 'AI 流程采集',
    description: '',
    params: { keyword: '新能源', max_pages: '3' },
  })
})

test('代码型（web）：锁定句 + 无 params 控件；保存不带 params', async () => {
  renderTab()
  await openEdit('web_page')
  expect(screen.getByText('代码型爬虫请在源码中修改')).toBeInTheDocument()
  expect(screen.queryByLabelText('入口地址')).not.toBeInTheDocument()
  expect(screen.queryByText('添加请求头')).not.toBeInTheDocument()
  expect(screen.queryByLabelText('keyword')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: SAVE_OK }))
  expect(await screen.findByText(SAVED_TOAST)).toBeInTheDocument()
  const payload = (updateDefinitionMeta as jest.Mock).mock.calls[0][1] as Record<string, unknown>
  expect(payload.title).toBe('网页采集')
  expect(payload).not.toHaveProperty('params')
})

test('删除被引用：确认弹窗原样展示后端拒绝句（含 #任务号），弹窗保持打开无假成功', async () => {
  ;(deleteDefinition as jest.Mock).mockRejectedValue({
    response: {
      data: {
        code: 'SPIDER_DEFINITION_IN_USE',
        message: '定义被历史任务引用：#101 #102 #103，删除前请先处理相关任务',
      },
    },
  })
  renderTab()
  // eslint-disable-next-line testing-library/no-node-access -- antd Table 行定位（仓库既有手法）
  const row = (await screen.findByText('news_api')).closest('tr')
  expect(row).not.toBeNull()
  fireEvent.click(within(row as HTMLElement).getByRole('button', { name: DELETE_BTN }))
  expect(await screen.findByText('确认删除定义：news_api')).toBeInTheDocument()
  // 确认弹窗内的删除按钮（圈定 .ant-modal，避开行内同名按钮）
  // eslint-disable-next-line testing-library/no-node-access -- 弹层圈定（仓库既有手法）
  const modal = document.querySelector('.ant-modal') as HTMLElement
  expect(modal).not.toBeNull()
  fireEvent.click(within(modal).getByRole('button', { name: DELETE_BTN }))
  expect(await screen.findByTestId('delete-reject-reason'))
    .toHaveTextContent('定义被历史任务引用：#101 #102 #103，删除前请先处理相关任务')
  // 弹窗保持打开、无假成功
  // eslint-disable-next-line testing-library/no-node-access -- 弹层断言（仓库既有手法）
  expect(document.querySelector('.ant-modal-title')?.textContent).toContain('确认删除定义')
  expect(screen.queryByText(/已删除/)).not.toBeInTheDocument()
})

test('非经办（viewer）无编辑/删除按钮（FR-103 守卫=经办，与 isAdmin 解耦）', async () => {
  mockUserState.current = VIEWER
  renderTab()
  await screen.findByText('资讯 API')
  expect(screen.queryByRole('button', { name: EDIT_BTN })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: DELETE_BTN })).not.toBeInTheDocument()
})

test('空态（GWT-103.4）：冻结句「还没有采集方案。」+ 说明与次链，旧句不残留', async () => {
  ;(fetchSpiderFiles as jest.Mock).mockResolvedValue({ items: [] })
  ;(fetchRegistry as jest.Mock).mockResolvedValue({ types: [], spiders: [] })
  renderTab()
  expect(await screen.findByText('还没有采集方案。')).toBeInTheDocument()
  expect(screen.getByText('创建入口在 AI 采集规划。')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '去 AI 采集规划' })).toBeInTheDocument()
  // 不是失败句：改前旧文案「未发现爬虫定义」必须消失
  expect(screen.queryByText('未发现爬虫定义')).not.toBeInTheDocument()
})
