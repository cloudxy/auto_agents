/**
 * 企业管理页增强（T-28 / FR-95）：GWT-95.1/95.2/95.3/95.5/95.7 UI 面 + GWT-94.2/94.3/94.4 呈现
 *
 * mock 边界：services 层（enterprise / rbac），api 拦截器语义不进本套；
 * 冲突句走真实 apiErrorMessage（shared）+ axios 形态 rejection，钉映射不钉实现
 * （Users.test / Members.test 同口径，P-FE-04/P-FE-05）。
 */
import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';

jest.mock('../services/rbac', () => ({
  createDepartment: jest.fn(),
  deleteDepartment: jest.fn(),
  listDepartments: jest.fn(() => Promise.resolve([])),
}));
jest.mock('../services/enterprise', () => ({
  createTenantMinimal: jest.fn(),
  listTenants: jest.fn(),
  renameTenant: jest.fn(),
  setTenantStatus: jest.fn(),
}));
jest.mock('antd', () => {
  const actual = jest.requireActual('antd');
  return {
    ...actual,
    message: { error: jest.fn(), success: jest.fn(), warning: jest.fn(), info: jest.fn() },
  };
});

import { message } from 'antd';
import { listTenants, renameTenant, setTenantStatus } from '../services/enterprise';
import EnterpriseManagement from './EnterpriseManagement';

const PLATFORM = {
  id: 1, slug: 'platform', name: '平台租户', status: 'active',
  expires_at: null, is_platform_default: true,
};
const REGULAR = {
  id: 2, slug: 'yunshu', name: '上海云枢科技', status: 'active',
  expires_at: null, is_platform_default: false,
};
const DISABLED = {
  id: 3, slug: 'demo', name: '示例公司', status: 'disabled',
  expires_at: null, is_platform_default: false,
};

const rows = (...ts: unknown[]) => Promise.resolve([...ts]);

const table = () => screen.getByRole('table');

/** 按公司名定位表格行（名称单元格 → tr） */
const rowOf = (name: string): HTMLElement => {
  const cell = within(table()).getByText(name);
  return cell.closest('tr') as HTMLElement;
};

beforeEach(() => {
  jest.clearAllMocks();
  (listTenants as jest.Mock).mockImplementation(() => rows(PLATFORM, REGULAR, DISABLED));
});

test('GWT-95.3 平台默认租户标注：行带「默认归属」Tag 一眼区分；无 AutoAgents 字样', async () => {
  render(<EnterpriseManagement />);
  expect(await screen.findByText('平台租户')).toBeInTheDocument();
  expect(screen.getByText('默认归属')).toBeInTheDocument(); // 平台默认租户行标注
  expect(screen.getByText('上海云枢科技')).toBeInTheDocument(); // 常规企业同行可见
  expect(screen.queryByText(/AutoAgents/)).toBeNull(); // §0.4 命名收口
});

test('GWT-94.2/94.3/94.4 平台租户守卫（UI 面）：改名/停用入口禁用 + 两句守卫句旁注；全表无删除企业控件', async () => {
  render(<EnterpriseManagement />);
  await screen.findByText('上海云枢科技');

  const platformRow = rowOf('平台租户');
  expect(within(platformRow).getByText('平台租户不可修改名称。')).toBeInTheDocument(); // GWT-94.2 守卫句
  expect(within(platformRow).getByText('平台租户不可停用。')).toBeInTheDocument(); // GWT-94.3 守卫句
  expect(within(platformRow).getByRole('button', { name: /改\s*名/ })).toBeDisabled();
  expect(within(platformRow).getByRole('button', { name: /停\s*用/ })).toBeDisabled();

  // 常规企业不受守卫影响
  expect(within(rowOf('上海云枢科技')).getByRole('button', { name: /改\s*名/ })).toBeEnabled();
  // GWT-94.4：常规企业与平台租户都无「删除企业」动作（前置冻结）
  expect(within(table()).queryByRole('button', { name: /删\s*除/ })).toBeNull();
});

test('GWT-95.1 改名成功：弹窗保存 → renameTenant → toast + 列表同显新名（同真相刷新）', async () => {
  render(<EnterpriseManagement />);
  await screen.findByText('上海云枢科技');

  fireEvent.click(within(rowOf('上海云枢科技')).getByRole('button', { name: /改\s*名/ }));
  const dialog = await screen.findByRole('dialog');
  expect(within(dialog).getByText('修改企业名称')).toBeInTheDocument();
  const input = within(dialog).getByLabelText('企业名称');
  expect((input as HTMLInputElement).value).toBe('上海云枢科技'); // 预填当前名

  fireEvent.change(input, { target: { value: '云枢集团' } });
  (renameTenant as jest.Mock).mockResolvedValueOnce(undefined);
  (listTenants as jest.Mock).mockImplementationOnce(() =>
    rows(PLATFORM, { ...REGULAR, name: '云枢集团' }, DISABLED));
  fireEvent.click(within(dialog).getByRole('button', { name: /保\s*存/ }));

  await waitFor(() => expect(renameTenant).toHaveBeenCalledWith(2, '云枢集团'));
  await waitFor(() => expect(message.success).toHaveBeenCalledWith('企业名称已更新。'));
  await waitFor(() => expect(screen.getByText('云枢集团')).toBeInTheDocument());
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
});

test('GWT-95.1 改名冲突：400 句原样内联呈现 + 内联句、弹窗不关、无内码、不 toast', async () => {
  render(<EnterpriseManagement />);
  await screen.findByText('上海云枢科技');

  fireEvent.click(within(rowOf('上海云枢科技')).getByRole('button', { name: /改\s*名/ }));
  const dialog = await screen.findByRole('dialog');
  fireEvent.change(within(dialog).getByLabelText('企业名称'), { target: { value: '平台租户' } });
  (renameTenant as jest.Mock).mockRejectedValueOnce({
    response: { status: 400, data: { success: false, code: 'BUSINESS_ERROR', message: '企业名称不可用: 平台租户', data: null } },
  });
  fireEvent.click(within(dialog).getByRole('button', { name: /保\s*存/ }));

  // 后端 400 句原样呈现（中文、无内码）
  expect(await within(dialog).findByText('企业名称不可用: 平台租户')).toBeInTheDocument();
  expect(within(dialog).getByText('“平台租户”与现有企业或保留名冲突，请更换名称。')).toBeInTheDocument();
  expect(screen.getByRole('dialog')).toBeInTheDocument(); // 弹窗不关（edge-states 错误）
  expect(within(dialog).queryByText(/BUSINESS_ERROR/)).toBeNull(); // X-QUOTA：可见处无内码
  expect(message.error).not.toHaveBeenCalled(); // 内联承担，不二次 toast
  expect((renameTenant as jest.Mock).mock.calls.length).toBe(1);
});

test('GWT-95.2 停用：确认弹窗后果句 → setTenantStatus(2, "disabled") → toast + 行状态「已停用」', async () => {
  render(<EnterpriseManagement />);
  await screen.findByText('上海云枢科技');

  fireEvent.click(within(rowOf('上海云枢科技')).getByRole('button', { name: /停\s*用/ }));
  expect(await screen.findByText('停用 “上海云枢科技”？')).toBeInTheDocument();
  const popover = await waitFor(() => {
    const pop = document.querySelector('.ant-popover') as HTMLElement;
    expect(pop).toBeTruthy();
    return pop;
  });
  expect(within(popover).getByText('停用后该企业用户将无法登录。')).toBeInTheDocument(); // 停用后果中文说明

  (setTenantStatus as jest.Mock).mockResolvedValueOnce(undefined);
  (listTenants as jest.Mock).mockImplementationOnce(() =>
    rows(PLATFORM, { ...REGULAR, status: 'disabled' }, DISABLED));
  fireEvent.click(within(popover).getByRole('button', { name: /停\s*用/ }));

  await waitFor(() => expect(setTenantStatus).toHaveBeenCalledWith(2, 'disabled'));
  await waitFor(() => expect(message.success).toHaveBeenCalledWith('企业已停用。'));
  await waitFor(() => expect(within(rowOf('上海云枢科技')).getByText('已停用')).toBeInTheDocument());
});

test('GWT-95.7 再启用：已停用行「启用」→ setTenantStatus(3, "active") → toast + 行回「启用」（双向流转）', async () => {
  render(<EnterpriseManagement />);
  await screen.findByText('示例公司');

  fireEvent.click(within(rowOf('示例公司')).getByRole('button', { name: /启\s*用/ }));
  (setTenantStatus as jest.Mock).mockResolvedValueOnce(undefined);
  (listTenants as jest.Mock).mockImplementationOnce(() =>
    rows(PLATFORM, REGULAR, { ...DISABLED, status: 'active' }));

  await waitFor(() => expect(setTenantStatus).toHaveBeenCalledWith(3, 'active'));
  await waitFor(() => expect(message.success).toHaveBeenCalledWith('企业已启用。'));
  await waitFor(() => expect(within(rowOf('示例公司')).getByText('启用')).toBeInTheDocument());
});

test('GWT-95.5 列表失败：失败句 + 重试，不是空表（FR-84 同句式）；重试后恢复', async () => {
  (listTenants as jest.Mock)
    .mockRejectedValueOnce(new Error('Network Error'))
    .mockImplementation(() => rows(PLATFORM, REGULAR, DISABLED));
  render(<EnterpriseManagement />);
  expect(await screen.findByText('企业列表加载失败。检查网络后重试。')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /重\s*试/ })).toBeInTheDocument();
  expect(screen.queryByText(/还没有企业/)).toBeNull(); // 失败 ≠ 空表

  fireEvent.click(screen.getByRole('button', { name: /重\s*试/ }));
  await waitFor(() => expect(screen.getByText('上海云枢科技')).toBeInTheDocument());
});

test('空态：公司 0 → 「还没有企业。」句（edge-states 企业管理屏），不是「暂无数据」', async () => {
  (listTenants as jest.Mock).mockImplementation(() => rows());
  render(<EnterpriseManagement />);
  expect(await screen.findByText('还没有企业。新建后出现在这里，可修改名称与账户状态。')).toBeInTheDocument();
  expect(screen.queryByText('暂无数据')).toBeNull();
});
