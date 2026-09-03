import React from 'react';
import { render, screen } from '@testing-library/react';
import App from './App';

// E0.3（工单 06）：替换 CRA "learn react" 腐坏模板测试。
// smoke 断言锚点 = 官网单页路由真实渲染：/ 渲染首页板块标题。
test('renders home page sections on the root route', async () => {
  window.history.replaceState({}, '', '/');
  render(<App />);
  const headings = await screen.findAllByRole('heading', { level: 2 });
  expect(headings.length).toBeGreaterThan(0);
});
