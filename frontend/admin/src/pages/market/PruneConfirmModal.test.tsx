/**
 * T-15（FR-02）+ D2 空根护栏：清理失源弹窗打开即 dry_run 取预览——
 * 正常零失源 → 「无需清理」；hub 根为空或不存在（skipped_reason=hub_root_empty）→
 * 警示根目录问题而不是告诉管理员一切正常；有失源 → 确认句 + 预览清单。
 */
import React from 'react'
import { render, screen } from '@testing-library/react'

import type { PruneMissingResult } from '../../services/capabilities'

jest.mock('../../feedback', () => {
  const actual = jest.requireActual('../../feedback')
  return {
    ...actual,
    message: { error: jest.fn(), success: jest.fn(), warning: jest.fn(), info: jest.fn() },
  }
})

jest.mock('../../services/capabilities', () => ({
  pruneMissingAssets: jest.fn(),
}))

import PruneConfirmModal, { PRUNE_ROOT_EMPTY, PRUNE_ZERO, PRUNE_ZERO_HINT } from './PruneConfirmModal'
import { pruneMissingAssets } from '../../services/capabilities'

const prune = pruneMissingAssets as jest.Mock

const result = (over: Partial<PruneMissingResult> = {}): PruneMissingResult => ({
  pruned: [],
  live_total: 3,
  reconcile_total: 3,
  disk_total: 3,
  skipped_reason: null,
  ...over,
})

const noop = () => undefined

const open = () => render(<PruneConfirmModal open onClose={noop} onPruned={noop} />)

beforeEach(() => {
  prune.mockReset()
})

test('零失源：显示「无需清理」，不显示根目录警示', async () => {
  prune.mockResolvedValue(result())
  open()
  expect(await screen.findByText(PRUNE_ZERO)).toBeInTheDocument()
  expect(screen.getByText(PRUNE_ZERO_HINT)).toBeInTheDocument()
  expect(screen.queryByTestId('prune-root-empty')).not.toBeInTheDocument()
  expect(prune).toHaveBeenCalledWith(true)
})

test('hub 根为空：警示根目录配置，不把「跳过」说成「无需清理」', async () => {
  prune.mockResolvedValue(result({ disk_total: 0, skipped_reason: 'hub_root_empty' }))
  open()
  expect(await screen.findByText(PRUNE_ROOT_EMPTY)).toBeInTheDocument()
  expect(screen.getByTestId('prune-root-empty')).toBeInTheDocument()
  expect(screen.queryByText(PRUNE_ZERO_HINT)).not.toBeInTheDocument()
})

test('有失源：确认句带数量并列出预览', async () => {
  prune.mockResolvedValue(result({ pruned: [{ asset_type: 'skill', name: 'gone-skill' }] }))
  open()
  expect(await screen.findByText('将下线 1 个无磁盘来源的资产')).toBeInTheDocument()
  expect(screen.getByText('gone-skill')).toBeInTheDocument()
})
