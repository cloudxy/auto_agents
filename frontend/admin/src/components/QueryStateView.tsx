/**
 * 管理端请求三态壳：错误与空态分开，避免把失败渲染成「暂无数据」。
 */
import React from 'react'
import { Alert, Empty, Spin } from 'antd'
import { queryViewState } from '@auto-agents/frontend-shared'

type Props<T> = {
  loading: boolean
  error?: string | null
  data: T | null | undefined
  isEmpty?: (data: T) => boolean
  children: (data: T) => React.ReactNode
}

export function QueryStateView<T>({ loading, error, data, isEmpty, children }: Props<T>) {
  const empty = data != null && isEmpty ? isEmpty(data) : data == null
  const state = queryViewState({ loading, error, data, isEmpty: empty })
  if (state === 'loading') {
    return (
      <div style={{ padding: 48, textAlign: 'center' }}>
        <Spin />
      </div>
    )
  }
  if (state === 'error') {
    return <Alert type="error" showIcon title={error || '加载失败'} />
  }
  if (state === 'empty') {
    return <Empty description="暂无数据" />
  }
  return <>{children(data as T)}</>
}
