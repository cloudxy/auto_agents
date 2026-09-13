import React from 'react';
import { render, screen } from '@testing-library/react';
import App from './App';
import { HERO_FIRST_SENTENCE } from './pages/Home';

jest.mock('./services/skills', () => ({
  listPublicSkills: jest.fn().mockRejectedValue(new Error('public list unavailable')),
  getPublicSkill: jest.fn(),
}));

// E0.3（工单 06）：替换 CRA "learn react" 腐坏模板测试。
// smoke 断言锚点 = 官网单页路由真实渲染：/ 渲染首页板块标题。
test('renders home page sections on the root route', async () => {
  window.history.replaceState({}, '', '/');
  render(<App />);
  const headings = await screen.findAllByRole('heading', { level: 2 });
  expect(headings.length).toBeGreaterThan(0);
});

test('GWT-U04.1 root route first sentence is collection not payment', async () => {
  window.history.replaceState({}, '', '/');
  render(<App />);
  const first = await screen.findByTestId('hero-first-sentence');
  expect((first.textContent || '').trim().startsWith(HERO_FIRST_SENTENCE)).toBe(true);
  expect(HERO_FIRST_SENTENCE).toContain('粘贴链接');
  expect(HERO_FIRST_SENTENCE).toContain('出数');
  const copy = document.body.textContent || '';
  expect(copy).not.toContain('当前可买');
  expect(copy).not.toContain('订阅成功');
  expect(copy).not.toContain('支付成功');
  expect(copy).not.toContain('中转可买');
  expect(copy).not.toContain('编辑官网第一句');
});
