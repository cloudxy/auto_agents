/**
 * T-10（FR-05 / AD-8）：md 正文 GFM 渲染封装。
 * 红线：默认禁 raw HTML（不引入 rehype-raw，GWT-05.2 XSS 防线——载荷按文本渲染）；
 * 渲染异常降级 <pre> 纯文本（K2/NFR-04）；大文档渲染期正文区 Skeleton + aria-live
 * 「正在渲染正文…」（NFR-02，先给身份再给正文，不白屏）。
 */
import React, { useEffect, useState } from 'react'
import { Skeleton } from 'antd'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

/** 超过该行数进入「先骨架后正文」渲染路径（上限 5000 行见 NFR-02） */
const LARGE_MD_LINES = 300

class MarkdownBoundary extends React.Component<
  { children: React.ReactNode; md: string },
  { failed: boolean }
> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  render() {
    if (this.state.failed) {
      return <pre data-testid="markdown-fallback">{this.props.md}</pre>
    }
    return this.props.children
  }
}

const MarkdownBody: React.FC<{ md: string }> = ({ md }) => {
  const large = md.split('\n').length > LARGE_MD_LINES
  const [ready, setReady] = useState(!large)
  useEffect(() => {
    if (!large) {
      setReady(true)
      return undefined
    }
    setReady(false)
    const timer = setTimeout(() => { setReady(true) }, 0)
    return () => clearTimeout(timer)
  }, [md, large])

  if (!ready) {
    return (
      <div aria-live="polite" data-testid="markdown-rendering">
        <Skeleton active title paragraph={{ rows: 3 }} />
        <span>正在渲染正文…</span>
      </div>
    )
  }
  return (
    <div className="markdown-body" data-testid="markdown-body">
      <MarkdownBoundary md={md}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{md}</ReactMarkdown>
      </MarkdownBoundary>
    </div>
  )
}

export default MarkdownBody
