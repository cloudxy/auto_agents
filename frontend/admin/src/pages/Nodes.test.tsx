import React from 'react'
import { render, screen } from '@testing-library/react'
import { withQuery } from '../testUtils'

jest.mock('../services/admin', () => ({
  fetchNodesPage: jest.fn().mockResolvedValue({ items: [], total: 0 }),
}))

import Nodes from './Nodes'

test('renders worker nodes empty hint', async () => {
  render(withQuery(<Nodes />))
  expect(await screen.findByText(/Worker 节点/)).toBeInTheDocument()
})
