/**
 * T-25：登录回跳打开订阅弹窗，不自动提交。
 */
import React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

const perm = {
  hasPermission: () => true,
  isPlatformAdmin: false,
  role: 'operator',
  isAdmin: false,
  permissions: [] as string[],
  filteredMenus: [] as unknown[],
}

jest.mock('../services/capabilities', () => ({
  listAssets: jest.fn().mockResolvedValue({ total: 0, items: [] }),
  scanPlugins: jest.fn(),
  scanExperts: jest.fn(),
  createTeam: jest.fn(),
  verifyPlugin: jest.fn(),
  patchListing: jest.fn(),
  getPlugin: jest.fn(),
  fetchPublicCapability: jest.fn().mockResolvedValue({
    name: 'bounce-skill', hosts: ['grok', 'zcode', 'kimi', 'claude'], subscribable: true,
  }),
  subscribeCapability: jest.fn(),
  listInstalls: jest.fn(),
  importAssets: jest.fn(),
  listPublicAssets: jest.fn().mockResolvedValue({ items: [], total: 0, market_closed: false }),
  getPowerMarket: jest.fn().mockResolvedValue({ enabled: true }),
  putPowerMarket: jest.fn(),
}))

jest.mock('./Skills', () => () => <div>skills-tab</div>)

jest.mock('../hooks/usePermission', () => ({
  usePermission: () => perm,
}))

import Capabilities from './Capabilities'
import { subscribeCapability } from '../services/capabilities'

const subscribe = subscribeCapability as jest.Mock

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/capabilities" element={<Capabilities />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  perm.isPlatformAdmin = false
  perm.role = 'operator'
  subscribe.mockReset()
})

test('login bounce query opens modal without auto subscribe', async () => {
  renderAt('/capabilities?subscribeType=skill&subscribeName=bounce-skill')
  expect(await screen.findByText('订阅 bounce-skill')).toBeInTheDocument()
  await waitFor(() => expect(screen.getByRole('radio', { name: /Grok/ })).not.toBeDisabled())
  expect(subscribe).not.toHaveBeenCalled()
})

test('plugin tab listed is not verify and has no ADR-0001 copy', async () => {
  perm.isPlatformAdmin = true
  renderAt('/capabilities')
  fireEvent.click(screen.getByRole('tab', { name: '插件' }))
  expect(await screen.findByText('上架不等于验证通过')).toBeInTheDocument()
  expect(document.body.textContent).not.toMatch(/ADR-0001/)
  expect(document.body.textContent).not.toMatch(/插件经 MCP 验证后方可分发/)
})
