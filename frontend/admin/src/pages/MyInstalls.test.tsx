/**
 * T-26 我的安装：GWT-35.1…35.7 / 40.2。35.4 经办可卸黑名单行 ≠ 35.5 只读角色拒绝。
 */
import React from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import {
  DELISTED, DELISTED_RESUBSCRIBE, EMPTY_COPY, EMPTY_CTA, ENABLE_HOST, FORBIDDEN_RUNTIME,
  LOAD_FAIL, READONLY_UNINSTALL_TIP, TRUST_CONFIRM,
} from './installsCopy'
import type { InstallRow } from '../services/capabilities'

jest.mock('../services/capabilities', () => ({
  listInstalls: jest.fn(),
  patchInstall: jest.fn(),
  uninstallInstall: jest.fn(),
}))

jest.mock('../components/SubscribeModal', () => ({
  __esModule: true,
  default: () => <div>subscribe-modal</div>,
}))

jest.mock('../hooks/usePermission', () => ({
  usePermission: () => ({
    hasPermission: () => true,
    isPlatformAdmin: false,
    role: 'operator',
    isAdmin: false,
    permissions: [],
    filteredMenus: [],
  }),
}))

import MyInstalls from './MyInstalls'
import { listInstalls, patchInstall, uninstallInstall } from '../services/capabilities'

const list = listInstalls as jest.Mock
const patch = patchInstall as jest.Mock
const uninstall = uninstallInstall as jest.Mock

const row = (over: Partial<InstallRow> = {}): InstallRow => ({
  id: 1,
  asset_id: 10,
  asset_name: 'skill-a',
  asset_type: 'skill',
  host: 'grok',
  enabled: 1,
  trusted: 0,
  delisted: false,
  flags_locked: false,
  can_change_flags: true,
  can_uninstall: true,
  resubscribe_allowed: true,
  resubscribe_hint: null,
  ...over,
})

function renderPage() {
  return render(<MemoryRouter><MyInstalls /></MemoryRouter>)
}

beforeEach(() => {
  list.mockReset()
  patch.mockReset()
  uninstall.mockReset()
})

test('GWT-35.1 two rows both present and can uninstall', async () => {
  list.mockResolvedValue({
    total: 2,
    items: [
      row({ id: 1, asset_name: 'skill-a' }),
      row({ id: 2, asset_name: 'skill-b', host: 'claude' }),
    ],
  })
  renderPage()
  expect(await screen.findByText('skill-a')).toBeInTheDocument()
  expect(screen.getByText('skill-b')).toBeInTheDocument()
  expect(screen.getAllByRole('button', { name: '卸载' })).toHaveLength(2)
  expect(screen.getAllByRole('button', { name: '卸载' })[0]).not.toBeDisabled()
})

test('GWT-35.2 empty copy and back to market', async () => {
  list.mockResolvedValue({ total: 0, items: [] })
  renderPage()
  expect(await screen.findByText(EMPTY_COPY)).toBeInTheDocument()
  const cta = screen.getByRole('link', { name: EMPTY_CTA })
  expect(cta).toHaveAttribute('href', expect.stringMatching(/\/capabilities$/))
  expect(screen.queryByText(LOAD_FAIL)).not.toBeInTheDocument()
})

test('GWT-35.3 unlist residual stays, delisted, operator can uninstall, resubscribe disabled', async () => {
  list.mockResolvedValue({
    total: 1,
    items: [row({
      delisted: true,
      delisted_label: DELISTED,
      can_uninstall: true,
      resubscribe_allowed: false,
      resubscribe_hint: DELISTED_RESUBSCRIBE,
    })],
  })
  renderPage()
  expect(await screen.findByText(DELISTED)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '卸载' })).not.toBeDisabled()
  expect(screen.getByRole('button', { name: '再订' })).toBeDisabled()
  expect(screen.getByText(DELISTED_RESUBSCRIBE)).toBeInTheDocument()
})

test('GWT-35.4 blacklist row flags locked, operator can uninstall', async () => {
  list.mockResolvedValue({
    total: 1,
    items: [row({
      asset_name: 'black-row',
      flags_locked: true,
      can_change_flags: false,
      can_uninstall: true,
      resubscribe_allowed: false,
    })],
  })
  renderPage()
  expect(await screen.findByText('black-row')).toBeInTheDocument()
  const switches = screen.getAllByRole('switch')
  expect(switches).toHaveLength(2)
  expect(switches[0]).toBeDisabled()
  expect(switches[1]).toBeDisabled()
  expect(screen.getByRole('button', { name: '卸载' })).not.toBeDisabled()
  fireEvent.click(switches[0])
  expect(patch).not.toHaveBeenCalled()
})

test('GWT-35.7 uninstall removes that row others stay', async () => {
  list.mockResolvedValue({
    total: 2,
    items: [
      row({ id: 1, asset_name: 'keep-row' }),
      row({ id: 2, asset_name: 'drop-row' }),
    ],
  })
  uninstall.mockResolvedValue({ id: 2, deleted: true })
  renderPage()
  expect(await screen.findByText('drop-row')).toBeInTheDocument()
  fireEvent.click(within(screen.getByText('drop-row').closest('tr') as HTMLElement).getByRole('button', { name: '卸载' }))
  expect(await screen.findByText(/卸载「drop-row」在 Grok 的安装/)).toBeInTheDocument()
  const confirm = screen.getAllByRole('button', { name: '卸载' }).at(-1)
  fireEvent.click(confirm as HTMLElement)
  await waitFor(() => expect(uninstall).toHaveBeenCalledWith(2))
  await waitFor(() => expect(screen.queryByText('drop-row')).not.toBeInTheDocument())
  expect(screen.getByText('keep-row')).toBeInTheDocument()
})

test('GWT-35.5 readonly role refuses uninstall enable trust', async () => {
  list.mockResolvedValue({
    total: 1,
    items: [row({
      asset_name: 'black-row',
      flags_locked: true,
      can_change_flags: false,
      can_uninstall: false,
      resubscribe_allowed: false,
    })],
  })
  renderPage()
  expect(await screen.findByText('black-row')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '卸载' })).toBeDisabled()
  expect(screen.getByTitle(READONLY_UNINSTALL_TIP)).toBeInTheDocument()
  screen.getAllByRole('switch').forEach((el) => expect(el).toBeDisabled())
  fireEvent.click(screen.getByRole('button', { name: '卸载' }))
  expect(uninstall).not.toHaveBeenCalled()
  expect(patch).not.toHaveBeenCalled()
})

test('GWT-35.6 plugin uninstall confirm does not cascade skills', async () => {
  list.mockResolvedValue({
    total: 2,
    items: [
      row({ id: 1, asset_name: 'plug-a', asset_type: 'plugin' }),
      row({ id: 2, asset_name: 'child-skill', asset_type: 'skill' }),
    ],
  })
  renderPage()
  expect(await screen.findByText('plug-a')).toBeInTheDocument()
  fireEvent.click(within(screen.getByText('plug-a').closest('tr') as HTMLElement).getByRole('button', { name: '卸载' }))
  expect(await screen.findByText(/卸载插件「plug-a」在 Grok 的安装？其中的技能不会一并卸载。/)).toBeInTheDocument()
})

test('GWT-40.2 no host-running copy and no enable-host button', async () => {
  list.mockResolvedValue({ total: 1, items: [row()] })
  renderPage()
  expect(await screen.findByText('skill-a')).toBeInTheDocument()
  expect(document.body.textContent).not.toContain(FORBIDDEN_RUNTIME)
  expect(document.body.textContent).not.toContain(ENABLE_HOST)
  expect(screen.queryByRole('button', { name: /启用到宿主/ })).not.toBeInTheDocument()
})

test('load error is not empty copy', async () => {
  list.mockRejectedValue({ response: { data: { code: 'INTERNAL_SERVER_ERROR' } } })
  renderPage()
  expect(await screen.findByText(LOAD_FAIL)).toBeInTheDocument()
  expect(screen.queryByText(EMPTY_COPY)).not.toBeInTheDocument()
})

test('trust on opens confirm', async () => {
  list.mockResolvedValue({ total: 1, items: [row({ trusted: 0, can_change_flags: true })] })
  renderPage()
  expect(await screen.findByText('skill-a')).toBeInTheDocument()
  fireEvent.click(screen.getAllByRole('switch')[1])
  expect(await screen.findByText(TRUST_CONFIRM)).toBeInTheDocument()
  expect(patch).not.toHaveBeenCalled()
})
