import React from 'react'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

jest.mock('../store/useAuthStore', () => ({
  useAuthStore: (sel: (s: { login: () => void }) => unknown) =>
    sel({ login: jest.fn() }),
}))

import Login from './Login'

test('renders login form', () => {
  render(
    <MemoryRouter>
      <Login />
    </MemoryRouter>,
  )
  expect(screen.getByPlaceholderText('用户名')).toBeInTheDocument()
  expect(screen.getByPlaceholderText('密码')).toBeInTheDocument()
})
