import React from 'react';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import { useAuthStore } from './store/useAuthStore';

jest.mock('./services/menus', () => ({
  fetchDynamicMenus: jest.fn().mockResolvedValue([]),
}));

beforeEach(() => {
  useAuthStore.setState({
    token: null, user: null, isAuthenticated: false, rememberMe: false,
  })
})

test('redirects unauthenticated visitor to the login page', async () => {
  window.history.replaceState({}, '', '/dashboard');
  render(<App />);
  expect(window.location.pathname).toBe('/login');
  expect(await screen.findByPlaceholderText('用户名')).toBeInTheDocument();
  expect(await screen.findByPlaceholderText('密码')).toBeInTheDocument();
  expect(await screen.findByRole('button', { name: /登\s*录/ })).toBeInTheDocument();
});

test('unauthenticated missing page is 404 shell not login', async () => {
  window.history.replaceState({}, '', '/this-page-does-not-exist-t05');
  render(<App />);
  expect(await screen.findByText('页面不存在或已被移除')).toBeInTheDocument();
  expect(await screen.findByRole('button', { name: /返回工作台/ })).toBeInTheDocument();
  expect(screen.queryByText(/抱歉/)).not.toBeInTheDocument();
});

test('tenant company admin /platform-ops is same 404 shell (GWT-15.3 / GWT-43.3)', async () => {
  useAuthStore.setState({
    token: 't', isAuthenticated: true, rememberMe: false,
    user: {
      access_token: 't', token_type: 'bearer', username: 'boss',
      is_admin: true, role: 'admin', is_platform_admin: false, tenant_id: 3,
    },
  })
  window.history.replaceState({}, '', '/platform-ops')
  render(<App />)
  expect(await screen.findByText('页面不存在或已被移除')).toBeInTheDocument()
  expect(await screen.findByRole('button', { name: /返回工作台/ })).toBeInTheDocument()
  expect(screen.queryByText(/产品事实/)).not.toBeInTheDocument()
  expect(screen.queryByText(/分析/)).not.toBeInTheDocument()
})

test('tenant operator market analytics direct hit is same 404 shell (GWT-43.3)', async () => {
  useAuthStore.setState({
    token: 't', isAuthenticated: true, rememberMe: false,
    user: {
      access_token: 't', token_type: 'bearer', username: 'op',
      is_admin: false, role: 'operator', is_platform_admin: false, tenant_id: 3,
    },
  })
  window.history.replaceState({}, '', '/product-events')
  render(<App />)
  expect(await screen.findByText('页面不存在或已被移除')).toBeInTheDocument()
  expect(await screen.findByRole('button', { name: /返回工作台/ })).toBeInTheDocument()
  expect(screen.queryByText(/产品事实/)).not.toBeInTheDocument()
  expect(screen.queryByText(/市场分析/)).not.toBeInTheDocument()
})

test('operator /newapi stays 404 shell (SH-11 still no newapi write)', async () => {
  useAuthStore.setState({
    token: 't', isAuthenticated: true, rememberMe: false,
    user: {
      access_token: 't', token_type: 'bearer', username: 'op',
      is_admin: false, role: 'operator', is_platform_admin: false, tenant_id: 3,
    },
  })
  window.history.replaceState({}, '', '/newapi')
  render(<App />)
  expect(await screen.findByText('页面不存在或已被移除')).toBeInTheDocument()
  expect(screen.queryByText(/渠道/)).not.toBeInTheDocument()
})

test('tenant company admin /newapi is same 404 shell as missing page (GWT-07.3)', async () => {
  useAuthStore.setState({
    token: 't', isAuthenticated: true, rememberMe: false,
    user: {
      access_token: 't', token_type: 'bearer', username: 'boss',
      is_admin: true, role: 'admin', is_platform_admin: false, tenant_id: 3,
    },
  })
  window.history.replaceState({}, '', '/newapi');
  render(<App />);
  expect(await screen.findByText('页面不存在或已被移除')).toBeInTheDocument();
  expect(await screen.findByRole('button', { name: /返回工作台/ })).toBeInTheDocument();
  expect(screen.queryByText(/抱歉/)).not.toBeInTheDocument();
  expect(screen.queryByText(/渠道/)).not.toBeInTheDocument();
});

test('test_operator_no_direct_gateway_or_relay_token_entry', async () => {
  const forbiddenGateway = '直连平台网关'
  const forbiddenRelayToken = '我的中转令牌'
  const operator = {
    access_token: 't', token_type: 'bearer', username: 'op',
    is_admin: false, role: 'operator', is_platform_admin: false, tenant_id: 3,
  }
  const renderShell = (path: string) => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    useAuthStore.setState({
      token: 't', isAuthenticated: true, rememberMe: false, user: operator,
    })
    window.history.replaceState({}, '', path)
    return render(
      <QueryClientProvider client={client}>
        <App />
      </QueryClientProvider>,
    )
  }
  const assertNoDirectGatewayOrRelayToken = () => {
    const copy = document.body.textContent || ''
    expect(copy).not.toContain(forbiddenGateway)
    expect(copy).not.toContain(forbiddenRelayToken)
    expect(screen.queryByText(forbiddenGateway)).not.toBeInTheDocument()
    expect(screen.queryByText(forbiddenRelayToken)).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: forbiddenGateway })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: forbiddenRelayToken })).not.toBeInTheDocument()
  }

  const dash = renderShell('/dashboard')
  expect(await screen.findByText('AutoAgents')).toBeInTheDocument()
  assertNoDirectGatewayOrRelayToken()
  dash.unmount()

  const usage = renderShell('/usage')
  expect(await screen.findByText('AutoAgents')).toBeInTheDocument()
  assertNoDirectGatewayOrRelayToken()
  usage.unmount()
});
