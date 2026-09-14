/**
 * 用户管理页「已删除」筛选 + 恢复（T-25 / FR-93）：GWT-93.1/93.2/93.3/93.4/93.9 UI 面
 *
 * mock 边界：services 层（fetchUsersPage / restoreUser 等），api 拦截器语义不进本套。
 * 占用冲突句走真实 apiErrorMessage（shared）+ axios 形态 rejection，钉映射不钉实现。
 */
import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';

jest.mock('../services/admin', () => ({ fetchUsersPage: jest.fn() }));
jest.mock('../services/platformOps', () => ({ listTenants: jest.fn(() => Promise.resolve([])) }));
jest.mock('../services/rbac', () => ({ listDepartments: jest.fn(() => Promise.resolve([])) }));
jest.mock('../services/users', () => ({
  createUser: jest.fn(),
  updateUser: jest.fn(),
  deleteUser: jest.fn(),
  restoreUser: jest.fn(),
}));

jest.mock('antd', () => {
  const actual = jest.requireActual('antd');
  return {
    ...actual,
    message: { error: jest.fn(), success: jest.fn(), warning: jest.fn(), info: jest.fn() },
  };
});

import { message } from 'antd';
import { fetchUsersPage } from '../services/admin';
import { restoreUser } from '../services/users';
import Users from './Users';

const ACTIVE_USER = {
  id: 1, username: 'op-active', email: 'op@x.com', is_active: true, is_admin: false,
  role: 'operator', tenant_id: 2, tenant_name: 'Acme', deleted_at: null,
};
const DELETED_USER = {
  id: 9, username: 'ghost', email: 'ghost@x.com', is_active: false, is_admin: false,
  role: 'operator', tenant_id: 2, tenant_name: 'Acme',
  deleted_at: '2026-09-01T00:00:00Z',
};

const page = (items: unknown[], total = items.length) => Promise.resolve({ items, total });

const switchToDeleted = async () => {
  fireEvent.mouseDown(within(screen.getByTestId('status-filter')).getByRole('combobox'));
  fireEvent.click(await screen.findByTitle('已删除'));
};

const table = () => screen.getByRole('table');

beforeEach(() => {
  jest.clearAllMocks();
  (fetchUsersPage as jest.Mock).mockImplementation((p: { status?: string }) =>
    p?.status === 'deleted' ? page([DELETED_USER]) : page([ACTIVE_USER]));
});

test('GWT-M32 filter 已停用 shows inactive row only', async () => {
  const DISABLED = { ...ACTIVE_USER, id: 3, username: 'op-off', is_active: false }
  ;(fetchUsersPage as jest.Mock).mockImplementation((p: { status?: string }) =>
    p?.status === 'deleted' ? page([]) : page([ACTIVE_USER, DISABLED]))
  render(<Users />)
  await waitFor(() => expect(screen.getByText('op-active')).toBeInTheDocument())
  fireEvent.mouseDown(within(screen.getByTestId('status-filter')).getByRole('combobox'))
  fireEvent.click(await screen.findByTitle('已停用'))
  await waitFor(() => expect(screen.getByText('op-off')).toBeInTheDocument())
  expect(screen.queryByText('op-active')).toBeNull()
})

test('GWT-M32 seed admin cannot be deleted', async () => {
  const SEED = {
    id: 1, username: 'admin', email: 'admin@x.com', is_active: true, is_admin: true,
    role: 'admin', tenant_id: null, tenant_name: null, deleted_at: null, is_platform_admin: true,
  }
  ;(fetchUsersPage as jest.Mock).mockResolvedValue({ items: [SEED, ACTIVE_USER], total: 2 })
  render(<Users />)
  await waitFor(() => expect(screen.getByText('admin')).toBeInTheDocument())
  expect(screen.getByText('op-active')).toBeInTheDocument()
  expect(screen.getAllByRole('button', { name: /删\s*除/ })).toHaveLength(1)
})

test('GWT-93.2 默认视图：请求 status=active，已删行不出现', async () => {
  render(<Users />);
  await waitFor(() => expect(screen.getByText('op-active')).toBeInTheDocument());
  expect(fetchUsersPage).toHaveBeenCalledWith(expect.objectContaining({ status: 'active' }));
  expect(screen.queryByText('ghost')).toBeNull();
  expect(within(table()).queryByText('已删除')).toBeNull(); // 无已删标记
});

test('GWT-93.1 筛「已删除」：请求 status=deleted，行带已删标记、无编辑/删除动作', async () => {
  render(<Users />);
  await waitFor(() => expect(screen.getByText('op-active')).toBeInTheDocument());

  await switchToDeleted();

  await waitFor(() => expect(fetchUsersPage).toHaveBeenCalledWith(expect.objectContaining({ status: 'deleted' })));
  await waitFor(() => expect(screen.getByText('ghost')).toBeInTheDocument());
  expect(within(table()).getByText('已删除')).toBeInTheDocument(); // 行内状态 Tag
  expect(within(table()).queryByText('op-active')).toBeNull(); // 活跃用户不出现在该筛选
  // antd 两字按钮自动插空格（「编 辑」/「删 除」）：name 用 \s* 兼容形态
  expect(screen.queryByRole('button', { name: /编\s*辑/ })).toBeNull();
  expect(screen.queryByRole('button', { name: /删\s*除/ })).toBeNull();
});

test('GWT-93.3 恢复成功：确认弹窗文案 → toast → 行从已删筛选消失', async () => {
  // 已删视图随恢复翻转（在 restoreUser 内翻——重载发生在其 resolve 之后，无竞态）
  let restored = false;
  (fetchUsersPage as jest.Mock).mockImplementation((p: { status?: string }) => {
    if (p?.status === 'deleted') return restored ? page([]) : page([DELETED_USER]);
    return page([ACTIVE_USER]);
  });
  render(<Users />);
  await waitFor(() => expect(screen.getByText('op-active')).toBeInTheDocument());
  await switchToDeleted();
  await waitFor(() => expect(screen.getByText('ghost')).toBeInTheDocument());

  fireEvent.click(screen.getByRole('button', { name: /恢\s*复/ }));
  const dialog = await screen.findByRole('dialog');
  expect(within(dialog).getByText('恢复用户 “ghost”？')).toBeInTheDocument();
  expect(within(dialog).getByText('恢复后该用户回到用户列表并恢复为启用状态，可重新登录。')).toBeInTheDocument();

  (restoreUser as jest.Mock).mockImplementationOnce(async () => {
    restored = true;
    return { ...DELETED_USER, deleted_at: null, is_active: true };
  });
  fireEvent.click(within(dialog).getByRole('button', { name: /恢\s*复/ }));

  await waitFor(() => expect(restoreUser).toHaveBeenCalledWith(9));
  await waitFor(() => expect(message.success).toHaveBeenCalledWith('已恢复 “ghost”。该用户已回到用户列表。'));
  await waitFor(() => expect(screen.queryByText('ghost')).toBeNull()); // 已删筛选不再出现
});

test('GWT-93.4/93.8 占用冲突：内联中文句两行、弹窗不关、无内码、不重复 toast', async () => {
  render(<Users />);
  await waitFor(() => expect(screen.getByText('op-active')).toBeInTheDocument());
  await switchToDeleted();
  await waitFor(() => expect(screen.getByText('ghost')).toBeInTheDocument());

  fireEvent.click(screen.getByRole('button', { name: /恢\s*复/ }));
  const dialog = await screen.findByRole('dialog');
  (restoreUser as jest.Mock).mockRejectedValueOnce({
    response: { status: 400, data: { success: false, code: 'BUSINESS_ERROR', message: '用户名或邮箱已被现有用户占用', data: null } },
  });
  fireEvent.click(within(dialog).getByRole('button', { name: /恢\s*复/ }));

  expect(await within(dialog).findByText('用户名或邮箱已被现有用户占用。')).toBeInTheDocument();
  expect(within(dialog).getByText('该用户仍保留在已删除列表中。')).toBeInTheDocument();
  expect(within(dialog).getByRole('alert')).toBeInTheDocument();
  expect(screen.getByRole('dialog')).toBeInTheDocument(); // 弹窗不关
  expect(screen.queryByText(/BUSINESS_ERROR/)).toBeNull(); // X-QUOTA：可见处无内码
  expect(message.error).not.toHaveBeenCalled();
  expect((restoreUser as jest.Mock).mock.calls.length).toBe(1);
});

test('GWT-93.9 重复恢复（幂等 no-op 可判定面）：不重复报成功，静默刷新', async () => {
  render(<Users />);
  await waitFor(() => expect(screen.getByText('op-active')).toBeInTheDocument());
  await switchToDeleted();
  await waitFor(() => expect(screen.getByText('ghost')).toBeInTheDocument());

  fireEvent.click(screen.getByRole('button', { name: /恢\s*复/ }));
  const dialog = await screen.findByRole('dialog');
  // 后端 no-op 早退口径：在册且停用（真恢复必置 is_active=true）
  (restoreUser as jest.Mock).mockResolvedValueOnce({ ...DELETED_USER, deleted_at: null, is_active: false });
  fireEvent.click(within(dialog).getByRole('button', { name: /恢\s*复/ }));

  await waitFor(() => expect(restoreUser).toHaveBeenCalledWith(9));
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull()); // 弹窗关闭
  expect(message.success).not.toHaveBeenCalled(); // 不重复报成功
  await waitFor(() => expect((fetchUsersPage as jest.Mock).mock.calls.length).toBeGreaterThanOrEqual(3));
});

test('恢复失败（非占用，网络）：失败句内联、弹窗不关（FR-84 族）', async () => {
  render(<Users />);
  await waitFor(() => expect(screen.getByText('op-active')).toBeInTheDocument());
  await switchToDeleted();
  await waitFor(() => expect(screen.getByText('ghost')).toBeInTheDocument());

  fireEvent.click(screen.getByRole('button', { name: /恢\s*复/ }));
  const dialog = await screen.findByRole('dialog');
  (restoreUser as jest.Mock).mockRejectedValueOnce(new Error('Network Error'));
  fireEvent.click(within(dialog).getByRole('button', { name: /恢\s*复/ }));

  expect(await within(dialog).findByText(/恢复失败。/)).toBeInTheDocument();
  expect(within(dialog).getByText(/该用户仍保持已删除。/)).toBeInTheDocument();
  expect(screen.getByRole('dialog')).toBeInTheDocument();
});

test('离线点恢复：钉句「网络不可用，用户没有恢复。」弹窗不关、不发请求（edge-states 用户管理屏）', async () => {
  const onlineGetter = jest.spyOn(navigator, 'onLine', 'get').mockReturnValue(false)
  render(<Users />);
  await waitFor(() => expect(screen.getByText('op-active')).toBeInTheDocument());
  await switchToDeleted();
  await waitFor(() => expect(screen.getByText('ghost')).toBeInTheDocument());

  fireEvent.click(screen.getByRole('button', { name: /恢\s*复/ }));
  const dialog = await screen.findByRole('dialog');
  fireEvent.click(within(dialog).getByRole('button', { name: /恢\s*复/ }));

  expect(await within(dialog).findByText('网络不可用，用户没有恢复。')).toBeInTheDocument();
  expect(screen.getByRole('dialog')).toBeInTheDocument(); // 弹窗不关
  expect(restoreUser).not.toHaveBeenCalled(); // 离线不发请求
  onlineGetter.mockRestore();
});

test('空态：默认视图 0 行 → 「还没有用户。」+ 新建入口；已删筛选 0 行 → 保留句、无动作', async () => {
  (fetchUsersPage as jest.Mock).mockImplementation(() => page([]));
  render(<Users />);
  await waitFor(() => expect(screen.getByText('还没有用户。')).toBeInTheDocument());

  const placeholder = () => document.querySelector('.ant-table-placeholder') as HTMLElement;
  fireEvent.click(within(placeholder()).getByRole('button', { name: '新建用户' }));
  const createDialog = await screen.findByRole('dialog');
  expect(within(createDialog).getByText('初始密码')).toBeInTheDocument(); // 新建弹窗打开
  fireEvent.click(within(createDialog).getByRole('button', { name: /取\s*消/ }));

  await switchToDeleted();
  await waitFor(() => expect(screen.getByText('还没有已删除的用户。删除的用户会保留在这里，可恢复。')).toBeInTheDocument());
  expect(within(placeholder()).queryByRole('button', { name: '新建用户' })).toBeNull(); // 设计：➖ 无操作
});

test('错误态：列表加载失败 → 失败句 + 重试，不是空表（FR-84）', async () => {
  (fetchUsersPage as jest.Mock)
    .mockRejectedValueOnce(new Error('Network Error'))
    .mockImplementation(() => page([ACTIVE_USER]));
  render(<Users />);
  await waitFor(() => expect(screen.getByText('用户列表加载失败。检查网络后重试。')).toBeInTheDocument());
  expect(screen.getByRole('button', { name: /重\s*试/ })).toBeInTheDocument();
  expect(screen.queryByText(/还没有用户/)).toBeNull(); // 失败 ≠ 空表

  fireEvent.click(screen.getByRole('button', { name: /重\s*试/ }));
  await waitFor(() => expect((fetchUsersPage as jest.Mock).mock.calls.length).toBe(2));
  await waitFor(() => expect(screen.getByText('op-active')).toBeInTheDocument());
});

test('T-34 页头规范：无复述页名的标题卡，筛选与新建保留在内容区（GWT-99.1/99.3）', async () => {
  (fetchUsersPage as jest.Mock).mockImplementation(() => page([ACTIVE_USER]));
  render(<Users />);
  await waitFor(() => expect(screen.getByText('op-active')).toBeInTheDocument());
  // 页名「用户管理」唯一标题在顶栏：页内不再有「用户管理（共 N 人）」标题卡
  expect(screen.queryByText(/用户管理（/)).toBeNull();
  expect(screen.queryByRole('heading')).toBeNull();
  // 内容区第一屏即业务内容：筛选行（含状态筛选）+ 用户表 + 新建动作（GWT-99.3 等价）
  expect(screen.getByTestId('status-filter')).toBeInTheDocument();
  expect(screen.getByRole('table')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /新建用户/ })).toBeInTheDocument();
  // 计数信息不丢：分页 showTotal 同屏承担
  expect(screen.getByText(/共 1 位用户/)).toBeInTheDocument();
});
