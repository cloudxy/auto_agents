import React from 'react'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import RelayGroups from './RelayGroups'

jest.mock('../services/relay', () => ({
  listRelayGroups: jest.fn().mockResolvedValue([
    { id: 1, name: 'default', rpm_limit: 0, tpm_limit: 0, models: [], status: 'enabled' },
  ]),
  listRelayTokens: jest.fn().mockResolvedValue([]),
  createRelayGroup: jest.fn(),
  patchRelayGroup: jest.fn(),
  issueRelayToken: jest.fn(),
  revokeRelayToken: jest.fn(),
}))

jest.mock('../hooks/usePermission', () => ({
  usePermission: () => ({
    hasPermission: () => true,
    role: 'admin',
    isAdmin: true,
    permissions: [],
    filteredMenus: [],
  }),
}))

test('shows tenant groups copy and not platform channel controls', async () => {
  render(
    <MemoryRouter>
      <RelayGroups />
    </MemoryRouter>,
  )
  expect(await screen.findByText('default')).toBeInTheDocument()
  expect(screen.getByText(/改不了/)).toBeInTheDocument()
  expect(screen.queryByText('我的中转令牌')).not.toBeInTheDocument()
  expect(screen.queryByText('直连平台网关')).not.toBeInTheDocument()
  expect(screen.queryByText('中转站管控')).not.toBeInTheDocument()
})
