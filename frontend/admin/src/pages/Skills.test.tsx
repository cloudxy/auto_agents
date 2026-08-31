/**
 * 技能中心页 smoke（工单 12）：mock services 后渲染列表壳与只读提示。
 */
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import Skills from './Skills';

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

test('renders skill list with dual score columns', async () => {
  render(<Skills />);
  expect(await screen.findByText('阿尔法')).toBeInTheDocument();
  await waitFor(() => expect(screen.getByText('8.6')).toBeInTheDocument());
  expect(screen.getByText('贝塔')).toBeInTheDocument();
  // AI 建议分列存在
  expect(screen.getByText('7.0')).toBeInTheDocument();
});

test('readonly mode hides correction column and shows hint', () => {
  render(<Skills canEdit={false} />);
  expect(screen.getByText(/当前角色只读/)).toBeInTheDocument();
  expect(screen.queryByText('矫正')).toBeNull();
});
