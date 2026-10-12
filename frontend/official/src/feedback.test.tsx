/**
 * feedback 单源：挂着 FeedbackProvider 时 message / modal 走 App 实例（吃 ConfigProvider 的
 * 主题与 zh_CN 文案），没挂回退 antd 静态 API；业务源码不得绕过本模块直用 antd 静态反馈方法。
 * 注：setupAntdRender 的 render wrapper 自带一层 FeedbackProvider（与生产根部同路径）；
 * 实例路径的提示是树内 state 更新，调用包 act。
 */
import fs from 'fs'
import path from 'path'
import React from 'react'
import { act, render, screen } from '@testing-library/react'
import { ConfigProvider, Modal, message as antdMessage } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { FeedbackProvider, message, modal } from './feedback'

afterEach(() => {
  jest.restoreAllMocks()
})

test('falls back to the antd static message when no provider is mounted', () => {
  const staticSuccess = jest.spyOn(antdMessage, 'success').mockImplementation((() => undefined) as never)
  message.success('已保存')
  expect(staticSuccess).toHaveBeenCalledWith('已保存')
})

test('routes to the App instance while mounted and back to static after unmount', async () => {
  const staticSuccess = jest.spyOn(antdMessage, 'success')
  const { unmount } = render(<FeedbackProvider />)
  act(() => { message.success('实例提示') })
  expect(await screen.findByText('实例提示')).toBeInTheDocument()
  expect(staticSuccess).not.toHaveBeenCalled()

  unmount()
  staticSuccess.mockImplementation((() => undefined) as never)
  message.success('回退提示')
  expect(staticSuccess).toHaveBeenCalledWith('回退提示')
})

test('nested providers: unmounting the inner one hands back to the outer instance', async () => {
  const staticInfo = jest.spyOn(antdMessage, 'info')
  const { rerender } = render(<FeedbackProvider><FeedbackProvider /></FeedbackProvider>)
  rerender(<FeedbackProvider />)
  act(() => { message.info('外层仍接管') })
  expect(await screen.findByText('外层仍接管')).toBeInTheDocument()
  expect(staticInfo).not.toHaveBeenCalled()
})

test('modal.confirm renders through the instance with the ConfigProvider zh_CN locale', async () => {
  const staticConfirm = jest.spyOn(Modal, 'confirm')
  render(
    <ConfigProvider locale={zhCN}>
      <FeedbackProvider />
    </ConfigProvider>,
  )
  act(() => { modal.confirm({ title: '确认离开注册页？' }) })
  expect(await screen.findByRole('dialog')).toHaveTextContent('确认离开注册页？')
  // zh_CN 的确认/取消文案（两字按钮 antd 会插空格）；静态 Modal.confirm 未被调用
  expect(screen.getByRole('button', { name: /确\s*定/ })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /取\s*消/ })).toBeInTheDocument()
  expect(staticConfirm).not.toHaveBeenCalled()
})

// ---------------------------------------------------------------- 源码机械钉
const SRC = __dirname
const STATIC_IMPORT = /import\s*\{[^}]*\b(message|notification)\b[^}]*\}\s*from\s*['"]antd['"]/
const STATIC_MODAL = /\bModal\.(confirm|info|success|error|warning)\(/

function sourceFiles(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const full = path.join(dir, e.name)
    if (e.isDirectory()) return sourceFiles(full)
    return /\.tsx?$/.test(e.name) && !/\.test\.tsx?$/.test(e.name) ? [full] : []
  })
}

test('business code imports feedback APIs from ./feedback, never antd statics', () => {
  const offenders = sourceFiles(SRC)
    .filter((f) => path.basename(f) !== 'feedback.tsx')
    .filter((f) => {
      const code = fs.readFileSync(f, 'utf8')
      return STATIC_IMPORT.test(code) || STATIC_MODAL.test(code)
    })
    .map((f) => path.relative(SRC, f))
  expect(offenders).toEqual([])
})
