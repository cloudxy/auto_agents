/**
 * T-10（FR-05 / GWT-05.2 XSS 金标 P-03）：raw HTML 默认禁用——
 * <script>/<img onerror> 载荷按文本可见，不执行、不注入；GFM 表格/代码块结构化；
 * 空串由调用方处理；大文档先骨架后正文（NFR-02）。
 */
import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'

import MarkdownBody from './MarkdownBody'

test('GWT-05.2 <script> 与 <img onerror> 载荷按文本渲染，不执行不注入', () => {
  const { container } = render(
    <MarkdownBody md={'# 标题\n\n<script>alert(1)</script>\n\n<img src=x onerror=alert(2)>'} />,
  )
  // 不产生真实 script / img 节点
  expect(container.querySelector('script')).toBeNull()
  expect(container.querySelector('img')).toBeNull()
  // 载荷字符作为文本可见
  expect(container.textContent).toContain('<script>alert(1)</script>')
  expect(container.textContent).toContain('<img src=x onerror=alert(2)>')
})

test('GFM 表格与代码块呈结构化样式（table/pre 节点，非纯文本堆叠）', () => {
  const md = [
    '| 列A | 列B |',
    '| --- | --- |',
    '| 1 | 2 |',
    '',
    '```bash',
    'npm ci',
    '```',
  ].join('\n')
  const { container } = render(<MarkdownBody md={md} />)
  expect(container.querySelector('table')).toBeTruthy()
  expect(container.querySelectorAll('th')).toHaveLength(2)
  expect(container.querySelector('pre')).toBeTruthy()
  expect(container.textContent).toContain('npm ci')
})

test('大文档（>300 行）渲染期先出骨架 + 「正在渲染正文…」，随后正文出现', async () => {
  const big = Array.from({ length: 400 }, (_, i) => `第 ${i} 行内容`).join('\n')
  const { container } = render(<MarkdownBody md={big} />)
  expect(screen.getByTestId('markdown-rendering')).toBeInTheDocument()
  expect(container.textContent).toContain('正在渲染正文…')
  await waitFor(() => expect(screen.getByTestId('markdown-body')).toBeInTheDocument())
  expect(container.textContent).toContain('第 0 行内容')
})

test('链接只渲染受控锚点（无 javascript: 注入面）', () => {
  const { container } = render(<MarkdownBody md="[点我](javascript:alert(3))" />)
  const anchor = container.querySelector('a')
  // react-markdown 默认 urlTransform 过滤危险协议：不产生可执行 href
  expect(anchor ? anchor.getAttribute('href') : null).not.toContain('javascript:')
})
