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

/**
 * F-02（重审 major）：members 创建侧 422 未处理——删后同名重建点「创建」静默失败。
 * 钉住：422 占用 → 出现可理解提示（软删占位口径）；表单不清空、弹窗不关闭。
 */
import api from '../services/api';

const conflict422 = (msg: string) => ({
  response: {
    status: 422,
    data: { success: false, code: 'VALIDATION_ERROR', message: msg, data: null },
  },
});

test('create 422 (soft-deleted name conflict): toast with actionable copy, form kept (F-02)', async () => {
  render(<Members />);
  await waitFor(() => expect(screen.getByText('alice')).toBeInTheDocument());

  fireEvent.click(screen.getByRole('button', { name: /添加成员/ }));
  fireEvent.change(screen.getByLabelText('用户名'), { target: { value: 'alice' } });
  fireEvent.change(screen.getByLabelText('邮箱'), { target: { value: 'alice@acme.com' } });
  fireEvent.change(screen.getByLabelText('初始密码'), { target: { value: 'secret1' } });

  // 后端口径（member_service.create_member）：唯一性检查含软删行 → 422
  (api.post as jest.Mock).mockRejectedValueOnce(conflict422('成员名已存在: alice'));

  fireEvent.click(screen.getByRole('button', { name: /创\s*建/ }));

  // 可理解文案（含软删占位语义与可行动作），而非静默失败
  expect(await screen.findByText(/该用户名已被占用/)).toBeInTheDocument();
  expect(await screen.findByText(/不可恢复/)).toBeInTheDocument();
  // 表单不清空、弹窗不关闭（用户可直接改名重试）
  expect((screen.getByLabelText('用户名') as HTMLInputElement).value).toBe('alice');
  expect(screen.getByLabelText('初始密码')).toBeInTheDocument();
  expect(api.post).toHaveBeenCalledTimes(1);
});

test('create 422 (email taken): mapped copy shown, form kept (F-02)', async () => {
  render(<Members />);
  await waitFor(() => expect(screen.getByText('alice')).toBeInTheDocument());

  fireEvent.click(screen.getByRole('button', { name: /添加成员/ }));
  fireEvent.change(screen.getByLabelText('用户名'), { target: { value: 'alice2' } });
  fireEvent.change(screen.getByLabelText('邮箱'), { target: { value: 'dup@acme.com' } });
  fireEvent.change(screen.getByLabelText('初始密码'), { target: { value: 'secret1' } });

  (api.post as jest.Mock).mockRejectedValueOnce(conflict422('邮箱已注册: dup@acme.com'));

  fireEvent.click(screen.getByRole('button', { name: /创\s*建/ }));

  expect(await screen.findByText(/该邮箱已被占用/)).toBeInTheDocument();
  expect((screen.getByLabelText('邮箱') as HTMLInputElement).value).toBe('dup@acme.com');
});

test('reset password failure: backend message shown, modal kept (F-02 顺带)', async () => {
  render(<Members />);
  await waitFor(() => expect(screen.getByText('alice')).toBeInTheDocument());

  fireEvent.click(screen.getByRole('button', { name: '重置密码' }));
  fireEvent.change(screen.getByLabelText('新密码'), { target: { value: 'secret2' } });

  (api.post as jest.Mock).mockRejectedValueOnce({
    response: { status: 404, data: { success: false, code: 'NOT_FOUND', message: '成员 2 不存在', data: null } },
  });

  fireEvent.click(screen.getByRole('button', { name: /^\s*重\s*置\s*$/ }));

  // 后端 message 透传 + 弹窗保留可直接重试
  expect(await screen.findByText('成员 2 不存在')).toBeInTheDocument();
  expect((screen.getByLabelText('新密码') as HTMLInputElement).value).toBe('secret2');
});
