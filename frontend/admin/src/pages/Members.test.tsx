/**
 * 成员管理页 smoke（工单 38）：mock api.get 返回信封（拦截器语义），unwrap 解包。
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

jest.mock('../services/api', () => {
  const envelope = () => ({ success: true, code: 'SUCCESS', message: 'ok', data: mockMembers.current });
  return {
    __esModule: true,
    default: { get: jest.fn(() => Promise.resolve(envelope())), post: jest.fn(), patch: jest.fn(), delete: jest.fn() },
    unwrap: (e: { data: unknown }) => e.data,
  };
});

// babel-jest 工厂引用 mock* 前缀变量（render 时才读取，无 TDZ）——RelayGroups.test 同款
const mockUserState: { current: Record<string, unknown> | null } = { current: null };

jest.mock('../store/useAuthStore', () => ({
  useAuthStore: (sel: (s: { user: Record<string, unknown> | null }) => unknown) =>
    sel({ user: mockUserState.current }),
}));

jest.mock('antd', () => {
  const actual = jest.requireActual('antd');
  return {
    ...actual,
    message: {
      error: jest.fn(),
      success: jest.fn(),
      warning: jest.fn(),
      info: jest.fn(),
    },
  };
});

import { message } from 'antd';
import Members from './Members';

const OWNER_USER = { tenant_id: 1, tenant_role: 'owner', is_platform_admin: false };
const ADMIN_USER = { tenant_id: 1, tenant_role: 'admin', is_platform_admin: false };
const VIEWER_USER = { tenant_id: 1, tenant_role: 'viewer', is_platform_admin: false };

const OWNER_ROW = { id: 1, username: 'owner-acme', email: 'o@a.com', tenant_role: 'owner', is_active: true };
const ALICE_ROW = { id: 2, username: 'alice', email: 'a@a.com', tenant_role: 'operator', is_active: true };
// 名单夹具（容器式，GWT-89.2 需要切换为「单人企业」形态）
const mockMembers: { current: unknown[] } = { current: [OWNER_ROW, ALICE_ROW] };

beforeEach(() => {
  (message.error as jest.Mock).mockClear();
  (message.success as jest.Mock).mockClear();
  mockUserState.current = OWNER_USER; // 默认 owner：既有用例行为不变
  mockMembers.current = [OWNER_ROW, ALICE_ROW];
  (api.get as jest.Mock).mockClear();
  (api.post as jest.Mock).mockClear();
  (api.patch as jest.Mock).mockClear();
  (api.delete as jest.Mock).mockClear();
});

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
  fireEvent.change(screen.getByLabelText('登录名'), { target: { value: 'alice' } });
  fireEvent.change(screen.getByLabelText('邮箱'), { target: { value: 'alice@acme.com' } });
  fireEvent.change(screen.getByLabelText('初始密码'), { target: { value: 'secret1' } });

  // 后端口径（member_service.create_member）：唯一性检查含软删行 → 422
  (api.post as jest.Mock).mockRejectedValueOnce(conflict422('成员名已存在: alice'));

  fireEvent.click(screen.getByRole('button', { name: /创\s*建/ }));

  // antd 6 toast 不进 testing-library 容器；钉 message.error 映射文案
  await waitFor(() => {
    expect(message.error).toHaveBeenCalledWith(expect.stringMatching(/该用户名已被占用/));
  });
  expect((message.error as jest.Mock).mock.calls[0][0]).toMatch(/不可恢复/);
  // 表单不清空、弹窗不关闭（用户可直接改名重试）
  expect((screen.getByLabelText('登录名') as HTMLInputElement).value).toBe('alice');
  expect(screen.getByLabelText('初始密码')).toBeInTheDocument();
  expect(api.post).toHaveBeenCalledTimes(1);
});

test('create 422 (email taken): mapped copy shown, form kept (F-02)', async () => {
  render(<Members />);
  await waitFor(() => expect(screen.getByText('alice')).toBeInTheDocument());

  fireEvent.click(screen.getByRole('button', { name: /添加成员/ }));
  fireEvent.change(screen.getByLabelText('登录名'), { target: { value: 'alice2' } });
  fireEvent.change(screen.getByLabelText('邮箱'), { target: { value: 'dup@acme.com' } });
  fireEvent.change(screen.getByLabelText('初始密码'), { target: { value: 'secret1' } });

  (api.post as jest.Mock).mockRejectedValueOnce(conflict422('邮箱已注册: dup@acme.com'));

  fireEvent.click(screen.getByRole('button', { name: /创\s*建/ }));

  await waitFor(() => {
    expect(message.error).toHaveBeenCalledWith(expect.stringMatching(/该邮箱已被占用/));
  });
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

  await waitFor(() => {
    expect(message.error).toHaveBeenCalledWith('成员 2 不存在');
  });
  expect((screen.getByLabelText('新密码') as HTMLInputElement).value).toBe('secret2');
});

/**
 * T-20（FR-89）：只读成员页看不见写控件——「点了再失败不算藏」，控件必须不渲染。
 * 后端 403 守卫为最终防线（backend/tests/test_saas_members.py::test_viewer_cannot_manage /
 * test_viewer_cannot_delete_member），前端职责=无入口。
 */
describe('T-20 FR-89 只读成员页隐藏写控件', () => {
  test('GWT-89.1 viewer：添加成员/角色下拉/重置密码/删除不渲染，名单可见', async () => {
    mockUserState.current = VIEWER_USER;
    render(<Members />);

    // 名单本身可见（owner 行 + 非 owner 行）
    await waitFor(() => expect(screen.getByText('owner-acme')).toBeInTheDocument());
    expect(screen.getByText('alice')).toBeInTheDocument();

    // 四控件不渲染（控件级断言，非 disabled/隐藏态）
    expect(screen.queryByRole('button', { name: /添加成员/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument(); // 角色下拉
    expect(screen.queryByRole('button', { name: '重置密码' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /删\s*除/ })).not.toBeInTheDocument();
    // 启用/停用开关同属写控件（patchMember is_active），只读视角只读 Tag 呈现
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
    expect(screen.getAllByText('启用')).toHaveLength(2);

    // 只读视角角色以下拉同形的 Tag 呈现（不再可改）
    expect(screen.getByText('operator')).toBeInTheDocument();
    expect(screen.getByText('owner')).toBeInTheDocument();
  });

  test('GWT-89.2 单人企业（接口成功）：负责人能看见自己', async () => {
    mockMembers.current = [OWNER_ROW]; // 企业只有负责人自己
    mockUserState.current = OWNER_USER;
    render(<Members />);

    await waitFor(() => expect(screen.getByText('owner-acme')).toBeInTheDocument());
    expect(screen.getByText('所有者')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /添加成员/ })).toBeInTheDocument();
  });

  test('GWT-89.2 只读打开同一企业：仍满足 89.1（名单可见+四控件不渲染）', async () => {
    mockMembers.current = [OWNER_ROW]; // 同一企业（负责人在名单里）
    mockUserState.current = VIEWER_USER;
    render(<Members />);

    await waitFor(() => expect(screen.getByText('owner-acme')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: /添加成员/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '重置密码' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /删\s*除/ })).not.toBeInTheDocument();
  });

  test('GWT-89.3 viewer 无入口：写 API（POST/PATCH/DELETE）全程未被调用', async () => {
    mockUserState.current = VIEWER_USER;
    render(<Members />);

    await waitFor(() => expect(screen.getByText('alice')).toBeInTheDocument());
    expect(api.post).not.toHaveBeenCalled();
    expect(api.patch).not.toHaveBeenCalled();
    expect(api.delete).not.toHaveBeenCalled();
    // 名单不变：接口仍成功返回原两行
    expect(screen.getByText('owner-acme')).toBeInTheDocument();
  });

  test('写侧不回归：admin 视角四控件仍渲染（守卫只藏只读，不误伤管理者）', async () => {
    mockUserState.current = ADMIN_USER;
    render(<Members />);

    await waitFor(() => expect(screen.getByText('alice')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /添加成员/ })).toBeInTheDocument();
    expect(screen.getByRole('combobox')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重置密码' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /删\s*除/ })).toBeInTheDocument();
  });
});

test('GWT-M21 add form has no 平台超管 option', async () => {
  render(<Members />);
  await waitFor(() => expect(screen.getByText('alice')).toBeInTheDocument());
  fireEvent.click(screen.getByRole('button', { name: /添加成员/ }));
  expect(screen.getByLabelText('登录名')).toBeInTheDocument();
  fireEvent.mouseDown(screen.getByLabelText('租户角色'));
  expect(screen.queryByText('平台超管')).not.toBeInTheDocument();
  expect(screen.queryByText('platform_admin')).not.toBeInTheDocument();
  expect(screen.getAllByText('admin（可管理成员）').length).toBeGreaterThan(0);
  expect(screen.getAllByText('viewer（只读）').length).toBeGreaterThan(0);
});

test('GWT-M21 empty login name: 请填写登录名, does not create', async () => {
  render(<Members />);
  await waitFor(() => expect(screen.getByText('alice')).toBeInTheDocument());
  fireEvent.click(screen.getByRole('button', { name: /添加成员/ }));
  fireEvent.change(screen.getByLabelText('邮箱'), { target: { value: 'n@a.com' } });
  fireEvent.change(screen.getByLabelText('初始密码'), { target: { value: 'secret1' } });
  fireEvent.click(screen.getByRole('button', { name: /创\s*建/ }));
  expect(await screen.findByText('请填写登录名')).toBeInTheDocument();
  expect(api.post).not.toHaveBeenCalled();
});

test('GWT-M21 cross-tenant 404 is same-shape, not 抱歉', async () => {
  (api.get as jest.Mock).mockRejectedValueOnce({
    response: { status: 404, data: { code: 'NOT_FOUND', message: 'not found' } },
  });
  render(
    <MemoryRouter>
      <Members />
    </MemoryRouter>,
  );
  expect(await screen.findByText('页面不存在或已被移除')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /返回工作台/ })).toBeInTheDocument();
  expect(screen.queryByText(/抱歉/)).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /添加成员/ })).not.toBeInTheDocument();
});
