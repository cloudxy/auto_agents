/**
 * T-10（FR-05）：抽屉全六态——GWT-05.1 四要素与 md 结构化渲染 / 05.2 XSS（载荷按
 * 文本不执行）/ 05.3 空态（示例区隐藏 + 暂无正文）/ 05.4 CTA 闸关钉句 /
 * 请求失败关抽屉+toast / 预览态未上架标记（OQ-D1）。
 */
import React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import type { PublicCapabilityCard } from '../../services/capabilities'

jest.mock('antd', () => {
  const actual = jest.requireActual('antd')
  return {
    ...actual,
    message: { error: jest.fn(), success: jest.fn(), warning: jest.fn(), info: jest.fn() },
  }
})

jest.mock('../../services/capabilities', () => ({
  fetchPublicCapability: jest.fn(),
}))

import { message } from 'antd'
import AssetDetailDrawer, {
  DRAWER_DETAIL_FAIL, DRAWER_EMPTY_MD, DRAWER_EMPTY_MD_HINT, DRAWER_GATE_CLOSED,
  EXAMPLES_TITLE,
} from './AssetDetailDrawer'
import { fetchPublicCapability } from '../../services/capabilities'

const fetchDetail = fetchPublicCapability as jest.Mock

const detail = (over: Partial<PublicCapabilityCard> = {}): PublicCapabilityCard => ({
  name: 'db-design',
  asset_type: 'skill',
  title: '数据库设计流水线',
  description: 'DBML 到迁移',
  listing_state: 'listed',
  subscribable: true,
  hosts: ['grok'],
  market_closed: false,
  gate_open: true,
  preview: true,
  skill_md: '# 标题\n\n正文段落',
  examples: null,
  ...over,
})

const noop = () => undefined

function renderDrawer(over: { open?: boolean } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <AssetDetailDrawer
        open={over.open ?? true}
        assetType="skill"
        name="db-design"
        canSubscribe
        onSubscribe={noop}
        onClose={noop}
      />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  fetchDetail.mockReset()
  ;(message.error as jest.Mock).mockClear()
  ;(message.success as jest.Mock).mockClear()
})

test('GWT-05.1 正常：banner/头像/标签/示例区/md 正文（表格与代码块结构化）', async () => {
  fetchDetail.mockResolvedValue(detail({
    skill_md: '# 数据库设计\n\n| 步骤 | 说明 |\n| --- | --- |\n| DBML | 建模 |\n\n```bash\ndbml-cli\n```',
    examples: ['输入 DBML 产出迁移'],
    origin_plugin_name: 'sdlc-workflow',
    featured: 1,
  }))
  const { container } = renderDrawer()
  await waitFor(() => expect(screen.getByTestId('asset-drawer')).toBeInTheDocument())
  // Drawer 渲染进 body portal：查 document 而非 render container
  expect(document.querySelector('.markdown-body table')).toBeTruthy()
  expect(document.querySelector('.markdown-body pre')).toBeTruthy()
  expect(screen.getByText('sdlc-workflow')).toBeInTheDocument()
  expect(screen.getByText(EXAMPLES_TITLE)).toBeInTheDocument()
  expect(screen.getByText('输入 DBML 产出迁移')).toBeInTheDocument()
  expect(screen.getByText('精选')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /订\s*阅/ })).toBeEnabled()
})

test('GWT-05.2 XSS：md 含 <script>/<img onerror> 载荷——按文本可见，不执行不注入', async () => {
  fetchDetail.mockResolvedValue(detail({
    skill_md: '# x\n\n<script>alert(1)</script>\n\n<img src=x onerror=alert(2)>',
  }))
  const { container } = renderDrawer()
  await waitFor(() => expect(screen.getByTestId('asset-drawer')).toBeInTheDocument())
  const drawerBody = document.querySelector('.ant-drawer-body') as HTMLElement
  expect(drawerBody.querySelector('script')).toBeNull()
  expect(drawerBody.querySelector('img')).toBeNull()
  expect(drawerBody.textContent).toContain('<script>alert(1)</script>')
  expect(drawerBody.textContent).toContain('<img src=x onerror=alert(2)>')
  expect(container.querySelector('[data-testid="markdown-fallback"]')).toBeNull()
})

test('GWT-05.3 空态：无示例维护示例区整体隐藏；md 空 →「暂无正文」+ 说明句，其余区块正常', async () => {
  fetchDetail.mockResolvedValue(detail({ skill_md: '', body_md: '', persona_md: null }))
  renderDrawer()
  await waitFor(() => expect(screen.getByTestId('drawer-empty-md')).toBeInTheDocument())
  expect(screen.getByText(DRAWER_EMPTY_MD)).toBeInTheDocument()
  expect(screen.getByText(DRAWER_EMPTY_MD_HINT)).toBeInTheDocument()
  expect(screen.queryByText(EXAMPLES_TITLE)).not.toBeInTheDocument()
  expect(screen.getByText('数据库设计流水线')).toBeInTheDocument()
  // 独立渲染无 ConfigProvider autoInsertSpace:false：两字按钮 name 带空格（仓库既有教训）
  expect(screen.getByRole('button', { name: /订\s*阅/ })).toBeInTheDocument()
})

test('GWT-05.4 CTA 闸关（管理员预览态按真实 gate_open）：禁用 + 钉句，点击无动作', async () => {
  const onSubscribe = jest.fn()
  fetchDetail.mockResolvedValue(detail({ gate_open: false, market_closed: false }))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AssetDetailDrawer
        open assetType="skill" name="db-design" canSubscribe
        onSubscribe={onSubscribe} onClose={noop}
      />
    </QueryClientProvider>,
  )
  const cta = await screen.findByRole('button', { name: DRAWER_GATE_CLOSED })
  expect(cta).toBeDisabled()
  fireEvent.click(cta)
  expect(onSubscribe).not.toHaveBeenCalled()
})

test('详情请求失败（网络级）：关闭抽屉 + toast「详情加载失败，请重试」', async () => {
  fetchDetail.mockRejectedValue(new Error('network down'))
  renderDrawer()
  await waitFor(() => expect(message.error).toHaveBeenCalledWith(DRAWER_DETAIL_FAIL))
})

test('OQ-D1 预览态 unlisted：附「未上架」标记；install_count=0 时元信息计数不显示', async () => {
  fetchDetail.mockResolvedValue(detail({
    listing_state: 'unlisted',
    preview: true,
    install_count: 0,
    updated_at: '2026-09-01T10:00:00',
  }))
  renderDrawer()
  await waitFor(() => expect(screen.getByTestId('asset-drawer')).toBeInTheDocument())
  expect(screen.getByText('未上架')).toBeInTheDocument()
  expect(screen.queryByText(/已订阅/)).not.toBeInTheDocument()
  expect(screen.getByText('更新于 2026-09-01')).toBeInTheDocument()
})

test('QA-11 预览态 install_count>=1 时元信息显示「已订阅 N 次」（两分支都钉，不只测 0 那半）', async () => {
  fetchDetail.mockResolvedValue(detail({
    listing_state: 'unlisted',
    preview: true,
    install_count: 3,
    updated_at: '2026-09-01T10:00:00',
  }))
  renderDrawer()
  await waitFor(() => expect(screen.getByTestId('asset-drawer')).toBeInTheDocument())
  expect(screen.getByText(/已订阅 3 次/)).toBeInTheDocument()
})

test('示例 [复制]：clipboard 写入 + toast「已复制到剪贴板」', async () => {
  const writeText = jest.fn().mockResolvedValue(undefined)
  Object.assign(navigator, { clipboard: { writeText } })
  fetchDetail.mockResolvedValue(detail({ examples: ['复制我'] }))
  renderDrawer()
  fireEvent.click(await screen.findByRole('button', { name: '复制这条示例' }))
  await waitFor(() => expect(writeText).toHaveBeenCalledWith('复制我'))
  await waitFor(() => expect(message.success).toHaveBeenCalled())
})
