/**
 * T-36 一键导入向导（FR-100 UI 半 / ADR-0023）：三步流转 / 失败原因逐条 /
 * 跳过标记（100.8）/ 越权无入口（100.6）/ 空批次（100.3）/ 二选一互斥 / 网络句。
 * 向导行为直接挂 ImportWizard（轻渲染）；入口/完成流转挂整页（Capabilities）。
 */
import React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import type { AssetRow, ImportResult } from '../services/capabilities'
import ImportWizard from './market/ImportWizard'
import {
  IMPORT_CHOOSE_HINT, IMPORT_EMPTY_BATCH, IMPORT_EXCLUSIVE,
  IMPORT_NETWORK_FAIL, IMPORT_STATUS_FAIL, IMPORT_STATUS_SKIP,
  IMPORT_UNLISTED_NOTE, summaryCopy,
} from './market/importWizardCopy'

const perm = {
  hasPermission: () => true,
  isPlatformAdmin: true,
  role: 'admin',
  isAdmin: true,
  permissions: [] as string[],
  filteredMenus: [] as unknown[],
}

jest.mock('../services/capabilities', () => ({
  listAssets: jest.fn().mockResolvedValue({ total: 0, items: [] }),
  listSources: jest.fn().mockResolvedValue({ total: 0, items: [] }),
  registerSource: jest.fn(),
  syncSource: jest.fn(),
  scanPlugins: jest.fn(),
  createTeam: jest.fn(),
  verifyPlugin: jest.fn(),
  patchListing: jest.fn(),
  getPlugin: jest.fn(),
  fetchPublicCapability: jest.fn(),
  subscribeCapability: jest.fn(),
  listInstalls: jest.fn(),
  importAssets: jest.fn(),
  listPublicAssets: jest.fn().mockResolvedValue({ items: [], total: 0, market_closed: false }),
  getPowerMarket: jest.fn().mockResolvedValue({ enabled: true }),
  putPowerMarket: jest.fn(),
}))

jest.mock('./Skills', () => () => <div>skills-tab</div>)

jest.mock('../hooks/usePermission', () => ({
  usePermission: () => perm,
}))

import Capabilities from './Capabilities'
import { importAssets, listAssets } from '../services/capabilities'

const runImport = importAssets as jest.Mock
const list = listAssets as jest.Mock

const result = (over: Partial<ImportResult> = {}): ImportResult => ({
  batch_id: 1,
  origin: 'upload',
  status: 'completed',
  total: 1,
  succeeded: 1,
  failed: 0,
  skipped: 0,
  items: [{ asset_type: 'skill', name: 'skill-a', status: 'succeeded', asset_id: 11 }],
  ...over,
})

const row = (over: Partial<AssetRow> = {}): AssetRow => ({
  id: 11,
  asset_type: 'skill',
  name: 'skill-a',
  title: 'skill-a',
  category: 'cat',
  status: 'stable',
  sync_state: 'ok',
  listing_state: 'unlisted',
  listed_at: null,
  source_type: 'import',
  ...over,
})

const md = (name: string): File => new File(['---\nname: x\n---'], name, { type: 'text/markdown' })

const modalEl = (): HTMLElement => document.querySelector('.ant-modal') as HTMLElement

const cancelSpy = jest.fn()
const finishSpy = jest.fn()

function renderWizard() {
  cancelSpy.mockClear()
  finishSpy.mockClear()
  render(<ImportWizard open onCancel={cancelSpy} onFinished={finishSpy} />)
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/capabilities']}>
        <Routes>
          <Route path="/capabilities" element={<Capabilities />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function pickFiles(names: string[]) {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement
  fireEvent.change(input, { target: { files: names.map(md) } })
}

beforeEach(() => {
  perm.isPlatformAdmin = true
  runImport.mockReset()
  list.mockReset()
  list.mockResolvedValue({ total: 0, items: [] })
})

test('GWT-100.2/100.5/100.7 失败原因逐条呈现（含路径逃逸与超大上限句）', async () => {
  runImport.mockResolvedValue(result({
    total: 3,
    succeeded: 1,
    failed: 2,
    items: [
      { asset_type: 'plugin', name: 'pack-a', status: 'succeeded', asset_id: 12 },
      {
        asset_type: 'skill',
        name: 'evil.md',
        status: 'failed',
        reason: '路径指向资产目录之外：evil.md，已拒绝',
      },
      {
        asset_type: 'command',
        name: 'big.zip',
        status: 'failed',
        reason: '文件超过大小上限（10485760 字节）：big.zip，已拒绝',
      },
    ],
  }))
  renderWizard()
  pickFiles(['pack-a.zip'])
  fireEvent.click(screen.getByRole('button', { name: '开始导入' }))
  expect(await within(modalEl()).findByText('路径指向资产目录之外：evil.md，已拒绝'))
    .toBeInTheDocument()
  expect(within(modalEl()).getByText('文件超过大小上限（10485760 字节）：big.zip，已拒绝'))
    .toBeInTheDocument()
  expect(within(modalEl()).getAllByText(IMPORT_STATUS_FAIL)).toHaveLength(2)
  expect(within(modalEl()).getByText(summaryCopy(1, 2, 0))).toBeInTheDocument()
})

test('GWT-100.8 幂等重导行标「已存在，跳过」，不计入失败', async () => {
  runImport.mockResolvedValue(result({
    total: 1,
    succeeded: 0,
    failed: 0,
    skipped: 1,
    items: [{ asset_type: 'agent', name: 'demo-agent', status: 'skipped' }],
  }))
  renderWizard()
  pickFiles(['demo-agent.md'])
  fireEvent.click(screen.getByRole('button', { name: '开始导入' }))
  expect(await within(modalEl()).findByText(IMPORT_STATUS_SKIP)).toBeInTheDocument()
  expect(within(modalEl()).queryByText(IMPORT_STATUS_FAIL)).toBeNull()
  expect(within(modalEl()).getByText(summaryCopy(0, 0, 1))).toBeInTheDocument()
  expect(within(modalEl()).queryByText(IMPORT_UNLISTED_NOTE)).toBeNull()
})

test('GWT-100.3 空批次中性句「没有可导入的资产。」+ 重新选择', async () => {
  runImport.mockResolvedValue(result({
    total: 0,
    succeeded: 0,
    failed: 0,
    skipped: 0,
    items: [],
    message: IMPORT_EMPTY_BATCH,
  }))
  renderWizard()
  pickFiles(['empty.zip'])
  fireEvent.click(screen.getByRole('button', { name: '开始导入' }))
  expect(await within(modalEl()).findByText(IMPORT_EMPTY_BATCH)).toBeInTheDocument()
  // 空批次不是静默成功也不是失败句：无失败 Alert，只给中性句 + 重新选择/完成
  expect(within(modalEl()).queryByRole('alert')).toBeNull()
  fireEvent.click(within(modalEl()).getByRole('button', { name: '重新选择' }))
  expect(within(modalEl()).getByText(IMPORT_CHOOSE_HINT)).toBeInTheDocument()
  expect(within(modalEl()).getByRole('button', { name: '开始导入' })).toBeDisabled()
})

test('文件与目录二选一互斥；目录路径单独成参', async () => {
  renderWizard()
  pickFiles(['a.md'])
  const dir = screen.getByLabelText('目录路径')
  expect(dir).toBeDisabled()
  expect(within(modalEl()).getByText(IMPORT_EXCLUSIVE)).toBeInTheDocument()
  fireEvent.click(document.querySelector('.ant-tag-close-icon') as HTMLElement)
  expect(dir).toBeEnabled()
  fireEvent.change(dir, { target: { value: '/srv/assets/pack' } })
  // 页头按钮带图标：antd icon 外层 aria-label 前缀，name 用子串匹配
  expect(screen.getByRole('button', { name: /选择文件/ })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: '开始导入' }))
  await waitFor(() => expect(runImport).toHaveBeenCalledTimes(1))
  expect(runImport.mock.calls[0][0]).toEqual({ directory: '/srv/assets/pack' })
})

test('网络失败句保留所选，可重试成功', async () => {
  runImport.mockRejectedValueOnce({})
  renderWizard()
  pickFiles(['skill-a.md'])
  fireEvent.click(screen.getByRole('button', { name: '开始导入' }))
  expect(await within(modalEl()).findByText(IMPORT_NETWORK_FAIL)).toBeInTheDocument()
  expect(within(modalEl()).getByText('skill-a.md')).toBeInTheDocument()
  runImport.mockResolvedValue(result())
  // 独立渲染无 ConfigProvider autoInsertSpace:false：两字按钮 name 带空格，用 /X\s*Y/
  fireEvent.click(within(modalEl()).getByRole('button', { name: /重\s*试/ }))
  expect(await within(modalEl()).findByText('已导入')).toBeInTheDocument()
})

test('导入中 loading 态：按钮 loading + 导入中…，完成后出结果', async () => {
  let resolveImport: (v: ImportResult) => void = () => undefined
  runImport.mockImplementation(() => new Promise<ImportResult>((res) => { resolveImport = res }))
  renderWizard()
  pickFiles(['skill-a.md'])
  fireEvent.click(screen.getByRole('button', { name: '开始导入' }))
  // 「导入中…」同时出现在进度区与按钮上；antd v6 loading 不落 disabled 属性，
  // 以 ant-btn-loading 类 + submit 的 pending 守卫防重复提交
  const busy = await within(modalEl()).findAllByText('导入中…')
  expect(busy.length).toBeGreaterThan(0)
  expect(within(modalEl()).getByRole('button', { name: /导入中…/ }).className)
    .toMatch(/ant-btn-loading/)
  resolveImport(result())
  expect(await within(modalEl()).findByText('已导入')).toBeInTheDocument()
})

test('GWT-100.4 四类类型中文化（技能/命令/智能体/插件）', async () => {
  runImport.mockResolvedValue(result({
    total: 4,
    succeeded: 4,
    items: [
      { asset_type: 'skill', name: 'a-skill', status: 'succeeded' },
      { asset_type: 'command', name: 'a-command', status: 'succeeded' },
      { asset_type: 'agent', name: 'a-agent', status: 'succeeded' },
      { asset_type: 'plugin', name: 'a-plugin', status: 'succeeded' },
    ],
  }))
  renderWizard()
  pickFiles(['bundle.zip'])
  fireEvent.click(screen.getByRole('button', { name: '开始导入' }))
  expect(await within(modalEl()).findByText('a-skill')).toBeInTheDocument()
  expect(within(modalEl()).getByText('技能')).toBeInTheDocument()
  expect(within(modalEl()).getByText('命令')).toBeInTheDocument()
  expect(within(modalEl()).getByText('智能体')).toBeInTheDocument()
  expect(within(modalEl()).getByText('插件')).toBeInTheDocument()
})

test('GWT-100.1 UI 三步流转：选文件→结果清单→完成，目录可见未上架新行', async () => {
  runImport.mockResolvedValue(result())
  renderPage()
  fireEvent.click(screen.getByRole('button', { name: /导入资产/ }))
  expect(screen.getByText(IMPORT_CHOOSE_HINT)).toBeInTheDocument()
  pickFiles(['skill-a.md'])
  expect(within(modalEl()).getByText('skill-a.md')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '开始导入' }))
  await waitFor(() => expect(runImport).toHaveBeenCalledTimes(1))
  expect(runImport.mock.calls[0][0].files).toHaveLength(1)
  expect(runImport.mock.calls[0][0].files[0].name).toBe('skill-a.md')
  // 结果清单：成功行含类型与名称 + 未上架注记；不出现「已上架」承诺
  expect(await within(modalEl()).findByText('skill-a')).toBeInTheDocument()
  expect(within(modalEl()).getByText('技能')).toBeInTheDocument()
  expect(within(modalEl()).getByText('已导入')).toBeInTheDocument()
  expect(within(modalEl()).getByText(IMPORT_UNLISTED_NOTE)).toBeInTheDocument()
  expect(within(modalEl()).getByText(summaryCopy(1, 0, 0))).toBeInTheDocument()
  expect(modalEl().textContent).not.toContain('已上架')
  // 完成：关闭向导，目录 tab 自动刷新出新行（未上架），不跳公开商店
  list.mockResolvedValue({ total: 1, items: [row()] })
  fireEvent.click(within(modalEl()).getByRole('button', { name: '完成' }))
  await screen.findByText('skill-a')
  await waitFor(() => expect(screen.queryByRole('button', { name: '完成' })).toBeNull())
  expect(list.mock.calls.length).toBeGreaterThanOrEqual(2)
  const group = screen.getByRole('group', { name: '上架 skill-a' })
  expect(within(group).getByText('未上架')).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: '目录' })).toHaveAttribute('aria-selected', 'true')
})

test('GWT-100.6 非超管无导入入口，页面其余照常', async () => {
  perm.isPlatformAdmin = false
  renderPage()
  expect(screen.queryByRole('button', { name: /导入资产/ })).toBeNull()
  expect(await screen.findByText('暂无已上架能力')).toBeInTheDocument()
  expect(screen.queryByRole('tab', { name: '源' })).not.toBeInTheDocument()
  expect(screen.queryByTestId('governance-shell')).not.toBeInTheDocument()
})
