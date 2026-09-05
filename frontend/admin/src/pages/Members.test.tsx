/**
 * 成员管理页 smoke（工单 38）：mock api.get 返回信封（拦截器语义），unwrap 解包。
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

jest.mock('../services/api', () => {
  const members = [
    { id: 1, username: 'owner-acme', email: 'o@a.com', tenant_role: 'owner', is_active: true },
    { id: 2, username: 'alice', email: 'a@a.com', tenant_role: 'operator', is_active: true },
  ];
  const envelope = { success: true, code: 'SUCCESS', message: 'ok', data: members };
  return {
    __esModule: true,
    default: { get: jest.fn(() => Promise.resolve(envelope)), post: jest.fn(), patch: jest.fn() },
    unwrap: (e: unknown) => (e as typeof envelope).data,
  };
});

import Members from './Members';

test('renders member list with owner row visible', async () => {
  render(<Members />);
  await waitFor(() => expect(screen.getByText('owner-acme')).toBeInTheDocument());
  expect(screen.getByText('alice')).toBeInTheDocument();
  expect(screen.getByText(/租户内部事务/)).toBeInTheDocument();
});

test('delete confirm copy matches backend semantics (audit preserved)', async () => {
  // T4/F-02：删除口径与后端软删实现对齐——账号移除、收件箱清空、审计保留
  render(<Members />);
  await waitFor(() => expect(screen.getByText('alice')).toBeInTheDocument());
  fireEvent.click(screen.getByRole('button', { name: '删除' })); // 非 owner 行的删除按钮
  await waitFor(() => expect(screen.getByText(/操作审计保留/)).toBeInTheDocument());
  expect(screen.getByText(/收件箱随之清空/)).toBeInTheDocument();
  expect(screen.getByText(/不可恢复/)).toBeInTheDocument();
});
