/**
 * 路由级错误边界（工单 69）
 *
 * 双层部署：App 根层（兜底一切）+ 路由层（页面崩只白屏该页，
 * 侧边栏导航仍可用）。antd Result 渲染 + 支持原地重试。
 */
import React from 'react'
import { Button, Result } from 'antd'

interface Props {
  children: React.ReactNode
  /** 边界标识（日志/面包屑用） */
  label?: string
}

interface State {
  error: Error | null
}

class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error(`[ErrorBoundary${this.props.label ? `:${this.props.label}` : ''}]`, error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <Result
          status="error"
          title="页面渲染出错"
          subTitle={this.state.error.message || '发生未知错误'}
          extra={[
            <Button key="retry" type="primary" onClick={() => this.setState({ error: null })}>
              重试
            </Button>,
            <Button key="home" onClick={() => { window.location.href = '/dashboard' }}>
              返回首页
            </Button>,
          ]}
        />
      )
    }
    return this.props.children
  }
}

export default ErrorBoundary
