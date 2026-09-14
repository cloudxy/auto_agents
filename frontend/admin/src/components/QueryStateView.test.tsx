import React from 'react'
import { render, screen } from '@testing-library/react'

import { QueryStateView } from './QueryStateView'

test('shows error instead of empty when request failed', () => {
  render(
    <QueryStateView loading={false} error="用量加载失败" data={null}>
      {() => <div>ready</div>}
    </QueryStateView>,
  )
  expect(screen.getByText('用量加载失败')).toBeInTheDocument()
  expect(screen.queryByText('暂无数据')).not.toBeInTheDocument()
  expect(screen.queryByText('ready')).not.toBeInTheDocument()
})

test('shows empty only when there is no error and no data', () => {
  render(
    <QueryStateView loading={false} error={null} data={null}>
      {() => <div>ready</div>}
    </QueryStateView>,
  )
  expect(screen.getByText('暂无数据')).toBeInTheDocument()
})

test('renders children when data is ready', () => {
  render(
    <QueryStateView loading={false} data={{ n: 1 }}>
      {(d) => <div>count {d.n}</div>}
    </QueryStateView>,
  )
  expect(screen.getByText('count 1')).toBeInTheDocument()
})
