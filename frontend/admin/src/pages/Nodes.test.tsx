/**
 * T-17 / FR-84（GWT-84.1/84.2）：节点屏失败≠空。
 * 失败 = 「节点状态加载失败。检查网络后重试。」+ 可点重试，不是「暂无在线节点」空表；
 * 真 0（接口成功且 0 节点）= 「还没有在线采集节点。」句，不是失败句。
 */
import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

jest.mock('../services/admin', () => ({
  fetchNodesPage: jest.fn().mockResolvedValue({ items: [], total: 0 }),
}))

import Nodes from './Nodes'
import { fetchNodesPage } from '../services/admin'

const renderNodes = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <Nodes />
    </QueryClientProvider>,
  )
}

test('GWT-84.1 nodes list failure shows failure sentence + retry, not forbidden empty copy', async () => {
  ;(fetchNodesPage as jest.Mock).mockRejectedValueOnce(new Error('network down'))
  renderNodes()
  expect(await screen.findByText('节点状态加载失败。检查网络后重试。')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /重\s*试/ })).toBeInTheDocument()
  // 禁句（FR-84 点名）：失败不得画成空表句或真 0 句
  expect(screen.queryByText(/暂无在线节点/)).not.toBeInTheDocument()
  expect(screen.queryByText(/还没有在线采集节点/)).not.toBeInTheDocument()
})

test('GWT-84.1 retry button refetches the nodes list', async () => {
  ;(fetchNodesPage as jest.Mock)
    .mockRejectedValueOnce(new Error('network down'))
    .mockResolvedValueOnce({
      items: [{ worker_id: 'w1', pid: 1, spiders: [], started_at: null, respawn_count: 0, online: true, active_tasks: [] }],
      total: 1,
    })
  renderNodes()
  expect(await screen.findByText('节点状态加载失败。检查网络后重试。')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /重\s*试/ }))
  expect(await screen.findByText('w1')).toBeInTheDocument()
  expect(screen.queryByText(/加载失败/)).not.toBeInTheDocument()
})

test('GWT-84.2 nodes true zero (200 + 0) shows 还没有在线采集节点 sentence, not failure', async () => {
  renderNodes()
  expect(await screen.findByText('还没有在线采集节点。没有在线工人时提交会被拦住，不会出数。')).toBeInTheDocument()
  expect(screen.queryByText(/加载失败/)).not.toBeInTheDocument()
  expect(screen.queryByText(/暂无在线节点/)).not.toBeInTheDocument()
})
