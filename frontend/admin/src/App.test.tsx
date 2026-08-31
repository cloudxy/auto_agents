import React from 'react';
import { render, screen } from '@testing-library/react';
import App from './App';

// E0.3（工单 06）：替换 CRA "learn react" 腐坏模板测试。
// smoke 断言锚点 = 路由壳真实行为：未认证访问受保护路由 → 重定向 /login 渲染登录页。
test('redirects unauthenticated visitor to the login page', () => {
  window.history.replaceState({}, '', '/dashboard');
  render(<App />);
  expect(window.location.pathname).toBe('/login');
  expect(screen.getByPlaceholderText('用户名')).toBeInTheDocument();
  expect(screen.getByPlaceholderText('密码')).toBeInTheDocument();
  // antd Button 对两字中文自动插空格（"登 录"），正则容忍空白
  expect(screen.getByRole('button', { name: /登\s*录/ })).toBeInTheDocument();
});
