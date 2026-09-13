/**
 * 技能中心页 smoke（工单 12）：mock services 后渲染列表壳与只读提示。
 * T-11：治理详情 SKILL.md 与商店面同一纯文本钉（FR-U13）。
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { withQuery } from '../testUtils';
import Skills from './Skills';
import { getSkillDetail } from '../services/skills';

jest.mock('../services/skills', () => ({
  listSkills: jest.fn().mockResolvedValue({
    total: 2,
    items: [
      { id: 1, name: 'alpha', title: '阿尔法', category: 'dev-tools', status: 'stable', sync_state: 'ok', score: 8.6, ai_suggested_score: 7.0 },
      { id: 2, name: 'beta', title: '贝塔', category: 'dev-tools', status: 'experimental', sync_state: 'ok' },
    ],
  }),
  getSkillDetail: jest.fn(),
  scanSkills: jest.fn(),
  correctSkillMeta: jest.fn(),
}));

// 工单 69：权限改为组件内 usePermission——测试统一 mock 只读权限
jest.mock('../hooks/usePermission', () => ({
  usePermission: () => ({
    hasPermission: () => false,
    role: 'viewer',
    isAdmin: false,
    permissions: [],
    filteredMenus: [],
  }),
}))


test('renders skill list with dual score columns', async () => {
  render(withQuery(<Skills />));
  expect(await screen.findByText('阿尔法')).toBeInTheDocument();
  await waitFor(() => expect(screen.getByText('8.6')).toBeInTheDocument());
  expect(screen.getByText('贝塔')).toBeInTheDocument();
  // AI 建议分列存在
  expect(screen.getByText('7.0')).toBeInTheDocument();
});

test('readonly mode hides correction column and shows hint', () => {
  render(withQuery(<Skills />));
  expect(screen.getByText(/当前角色只读/)).toBeInTheDocument();
  expect(screen.queryByText('矫正')).toBeNull();
});

test('GWT-U13.1 admin SKILL.md is text: <script>alert(1)</script> visible, no script/img', async () => {
  const payload = '<script>alert(1)</script> <img src=x onerror=alert(1)>';
  const alertSpy = jest.spyOn(window, 'alert').mockImplementation(() => {});
  (getSkillDetail as jest.Mock).mockResolvedValue({
    id: 1,
    name: 'alpha',
    title: '阿尔法',
    category: 'dev-tools',
    status: 'stable',
    source_type: 'local',
    sync_state: 'ok',
    skill_md: payload,
    reviews: [],
  });
  render(withQuery(<Skills />));
  fireEvent.click(await screen.findByText('阿尔法'));
  const body = await screen.findByTestId('skill-md');
  expect(body.textContent).toContain('<script>alert(1)</script>');
  expect(body.textContent).toContain('onerror');
  expect(body.innerHTML).toContain('&lt;script&gt;');
  expect(body.querySelector('script')).toBeNull();
  expect(body.querySelector('img')).toBeNull();
  expect(document.querySelector('img[src="x"]')).toBeNull();
  expect(alertSpy).not.toHaveBeenCalled();
  expect(document.body.textContent || '').not.toContain('当前可买');
  alertSpy.mockRestore();
});
