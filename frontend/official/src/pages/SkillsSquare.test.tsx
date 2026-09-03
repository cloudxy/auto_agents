/**
 * 技能广场页测试（工单 19）：渲染 + 不可信内容安全渲染（XSS payload 只成为文本）。
 */
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const XSS_PAYLOAD = '<script>alert("xss")</script> <img src=x onerror=alert(1)>';

jest.mock('../services/skills', () => ({
  listPublicSkills: jest.fn().mockResolvedValue({
    total: 1,
    items: [
      { name: 'alpha', title: '阿尔法技能', description: '官方推荐技能', category: 'dev-tools', status: 'recommended', tier: 'S', score: 8.6 },
    ],
  }),
  getPublicSkill: jest.fn().mockResolvedValue({
    name: 'alpha', title: '阿尔法技能', description: 'd', category: 'dev-tools',
    status: 'recommended', tier: 'S', skill_md: `# 正文\n\n${XSS_PAYLOAD}`,
  }),
}));

import SkillsSquare from './SkillsSquare';

const renderPage = () =>
  render(
    <MemoryRouter>
      <SkillsSquare />
    </MemoryRouter>
  );

test('renders published skill cards from public API', async () => {
  renderPage();
  expect(await screen.findByText('阿尔法技能')).toBeInTheDocument();
  expect(screen.getByText('dev-tools')).toBeInTheDocument();
});

test('skill md renders untrusted content as escaped text only', async () => {
  const { container } = renderPage();
  (await screen.findByText('阿尔法技能')).click();
  await waitFor(() => expect(screen.getByTestId('skill-md')).toBeInTheDocument());
  const mdNode = screen.getByTestId('skill-md');
  // payload 以纯文本可见（React 转义），不存在可执行节点
  expect(mdNode.textContent).toContain('<script>');
  expect(container.querySelector('script')).toBeNull();
  expect(container.querySelector('img[src="x"]')).toBeNull();
});
