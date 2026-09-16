/**
 * T-12（FR-07 UI 面 / AD-4a / NFR-08）：目录导入向导。
 *
 * GWT 锚：07.1 三步流转与预览计数、07.2 取消零写入（不发 confirm）、07.3 更新标注、
 * 07.4 空态句、07.5 逐条失败原因、07.6 >500 前端预检 + [使用服务器路径] 出口、
 * 07.9 跳过清单（非白名单）+ QA-8 非法路径同清单。
 *
 * 上传形态断言（AD-4a 前端契约）：form part 的 filename 必须是 webkitRelativePath，
 * 服务端按树判型——这条错了后端判型全盘失效，故单列一个用例钉。
 */
import React from 'react'
import { ConfigProvider } from 'antd'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

jest.mock('antd', () => {
  const actual = jest.requireActual('antd')
  return {
    ...actual,
    message: { error: jest.fn(), success: jest.fn(), warning: jest.fn(), info: jest.fn() },
  }
})

jest.mock('../../services/capabilities', () => ({
  previewTreeImport: jest.fn(),
  confirmTreeImport: jest.fn(),
}))

import { message } from 'antd'
import ImportTreePicker, {
  TREE_CANCEL_TOAST, TREE_EMPTY_TITLE, TREE_OVER_LIMIT, TREE_SELECT_DIR, TREE_START_PARSE,
  TREE_USE_SERVER,
} from './ImportTreePicker'
import { confirmTreeImport, previewTreeImport } from '../../services/capabilities'

const preview = previewTreeImport as jest.Mock
const confirm = confirmTreeImport as jest.Mock

const renderPicker = (over: Partial<React.ComponentProps<typeof ImportTreePicker>> = {}) => {
  const props = {
    open: true,
    onCancel: jest.fn(),
    onFinished: jest.fn(),
    onUseServerPath: jest.fn(),
    ...over,
  }
  render(
    <ConfigProvider button={{ autoInsertSpace: false }}>
      <ImportTreePicker {...props} />
    </ConfigProvider>,
  )
  return props
}

/** 造一个带 webkitRelativePath 的 File（jsdom 不会自己填这个只读属性） */
const relFile = (rel: string): File => {
  const file = new File(['x'], rel.split('/').pop() || 'f', { type: 'text/markdown' })
  Object.defineProperty(file, 'webkitRelativePath', { value: rel })
  return file
}

const pick = (rels: string[]) => {
  const input = screen.getByTestId('tree-dir-input') as HTMLInputElement
  const files = rels.map(relFile)
  Object.defineProperty(input, 'files', { value: files, configurable: true })
  fireEvent.change(input)
}

const TREE = ['up/alpha/SKILL.md', 'up/beta/SKILL.md', 'up/myplug/plugin.json']

const previewPayload = (over: Record<string, unknown> = {}) => ({
  assets: [
    { asset_type: 'skill', name: 'alpha', action: 'create', origin_path: '.agents/skills/alpha' },
    { asset_type: 'skill', name: 'beta', action: 'update', origin_path: '.agents/skills/beta' },
    {
      asset_type: 'plugin', name: 'myplug', action: 'create',
      origin_path: '.agents/plugins/myplug',
      bundled: [{ asset_type: 'skill', name: 'myplug__s1', action: 'create' }],
    },
  ],
  skipped: [],
  counts: { skill: 3, plugin: 1, command: 0, agent: 0 },
  files_total: 3,
  ...over,
})

beforeEach(() => {
  preview.mockReset()
  confirm.mockReset()
  ;(message.info as jest.Mock).mockClear()
})


// ---------- GWT-07.1 三步流转 ----------

test('GWT-07.1 选目录 → 预览（类型计数 + 新建/更新标注 + bundled）→ 确认 → 结果', async () => {
  preview.mockResolvedValue(previewPayload())
  confirm.mockResolvedValue({ created: 3, updated: 1, failed: [], skipped: [] })
  const props = renderPicker()

  pick(TREE)
  expect(await screen.findByText(/已选择：up · 3 个文件/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: TREE_START_PARSE }))

  expect(await screen.findByText(/共识别 3 项资产/)).toBeInTheDocument()
  expect(screen.getByText(/技能 3/)).toBeInTheDocument()
  expect(screen.getByText(/插件 1/)).toBeInTheDocument()
  expect(screen.getAllByText('新建').length).toBeGreaterThanOrEqual(2)
  expect(screen.getByText('更新')).toBeInTheDocument()       // GWT-07.3 标注
  expect(screen.getByText('myplug__s1')).toBeInTheDocument()  // bundled 折叠展示

  fireEvent.click(screen.getByRole('button', { name: '确认导入 3 项' }))
  expect(await screen.findByText(/导入完成：新建 3 · 更新 1 · 失败 0/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '完成' }))
  expect(props.onFinished).toHaveBeenCalled()
})


test('AD-4a 上传形态：part filename 必须是 webkitRelativePath（服务端按树判型）', async () => {
  preview.mockResolvedValue(previewPayload())
  renderPicker()
  pick(TREE)
  fireEvent.click(screen.getByRole('button', { name: TREE_START_PARSE }))
  await waitFor(() => expect(preview).toHaveBeenCalled())
  const sent: File[] = preview.mock.calls[0][0]
  expect(sent.map((f) => (f as File & { webkitRelativePath: string }).webkitRelativePath))
    .toEqual(TREE)
})


// ---------- GWT-07.2 取消零写入 ----------

test('GWT-07.2 预览步骤取消：不发 confirm + 零写入 toast', async () => {
  preview.mockResolvedValue(previewPayload())
  const props = renderPicker()
  pick(TREE)
  fireEvent.click(screen.getByRole('button', { name: TREE_START_PARSE }))
  await screen.findByText(/共识别 3 项资产/)

  fireEvent.click(screen.getByRole('button', { name: '取消' }))
  expect(confirm).not.toHaveBeenCalled()
  expect(message.info).toHaveBeenCalledWith(TREE_CANCEL_TOAST)
  expect(props.onCancel).toHaveBeenCalledWith(false)
})


// ---------- GWT-07.4 空态 ----------

test('GWT-07.4 无可判型资产：空态句 + 确认按钮禁用', async () => {
  preview.mockResolvedValue(previewPayload({
    assets: [], counts: { skill: 0, plugin: 0, command: 0, agent: 0 },
  }))
  renderPicker()
  pick(['up/notes/README.md'])
  fireEvent.click(screen.getByRole('button', { name: TREE_START_PARSE }))
  expect(await screen.findByText(TREE_EMPTY_TITLE)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '确认导入 0 项' })).toBeDisabled()
})


// ---------- GWT-07.5 部分失败 ----------

test('GWT-07.5 逐条失败原因列在结果清单，成功项照常计数', async () => {
  preview.mockResolvedValue(previewPayload())
  confirm.mockResolvedValue({
    created: 2, updated: 0,
    failed: [{ name: 'beta', reason: '标题解析失败' }],
    skipped: [],
  })
  renderPicker()
  pick(TREE)
  fireEvent.click(screen.getByRole('button', { name: TREE_START_PARSE }))
  await screen.findByText(/共识别 3 项资产/)
  fireEvent.click(screen.getByRole('button', { name: '确认导入 3 项' }))

  expect(await screen.findByText(/导入完成：新建 2 · 更新 0 · 失败 1/)).toBeInTheDocument()
  expect(screen.getByText('标题解析失败')).toBeInTheDocument()
  expect(screen.getByText('beta')).toBeInTheDocument()
})


// ---------- GWT-07.6 超限前端预检 ----------

test('GWT-07.6 >500 文件：开始解析禁用 + 不发请求；错误态给 [使用服务器路径] 出口', async () => {
  const props = renderPicker()
  pick(Array.from({ length: 501 }, (_, i) => `up/pad/f${i}.md`))
  expect(await screen.findByText(/已选择：up · 501 个文件/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: TREE_START_PARSE })).toBeDisabled()
  expect(preview).not.toHaveBeenCalled()
  expect(screen.getByText('当前 501 个')).toBeInTheDocument()
  expect(props.onUseServerPath).not.toHaveBeenCalled()
})


test('GWT-07.6 服务端 422 超限：逐字文案 + [使用服务器路径] 可点', async () => {
  preview.mockRejectedValue({ response: { status: 422, data: { message: TREE_OVER_LIMIT } } })
  const props = renderPicker()
  pick(TREE)
  fireEvent.click(screen.getByRole('button', { name: TREE_START_PARSE }))
  expect(await screen.findByText(TREE_OVER_LIMIT)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: TREE_USE_SERVER }))
  expect(props.onUseServerPath).toHaveBeenCalled()   // GWT-07.8 能力不回退
})


// ---------- GWT-07.9 + QA-8 跳过清单 ----------

test('GWT-07.9/QA-8 跳过清单：非白名单扩展名与非法路径各自带原因', async () => {
  preview.mockResolvedValue(previewPayload({
    skipped: [
      { path: 'up/alpha/payload.exe', reason: '非白名单扩展名' },
      { path: '../../etc/passwd.md', reason: '非法路径' },
    ],
  }))
  renderPicker()
  pick(TREE)
  fireEvent.click(screen.getByRole('button', { name: TREE_START_PARSE }))
  expect(await screen.findByText('已跳过 2 个文件')).toBeInTheDocument()
  expect(screen.getByText('up/alpha/payload.exe')).toBeInTheDocument()
  expect(screen.getByText('（非白名单扩展名）')).toBeInTheDocument()
  expect(screen.getByText('../../etc/passwd.md')).toBeInTheDocument()
  expect(screen.getByText('（非法路径）')).toBeInTheDocument()
})


// ---------- 网络失败可重试 ----------

test('网络失败：中性句 + 重试按钮，重试成功进入预览（保留所选）', async () => {
  preview.mockRejectedValueOnce({}).mockResolvedValueOnce(previewPayload())
  renderPicker()
  pick(TREE)
  fireEvent.click(screen.getByRole('button', { name: TREE_START_PARSE }))
  expect(await screen.findByText('导入没有开始：网络不可用。')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '重试' }))
  expect(await screen.findByText(/共识别 3 项资产/)).toBeInTheDocument()
})


test('弹窗标题与步骤条：三步（选择目录 / 导入预览 / 结果）', () => {
  renderPicker()
  expect(screen.getByText('导入预览')).toBeInTheDocument()
  expect(screen.getAllByText(TREE_SELECT_DIR).length).toBeGreaterThanOrEqual(1)
})
