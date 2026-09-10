/**
 * LLM 供应商页：只读无写控件；经办看得到本企业行保存/测试连接（GWT-73.4）。
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { withQuery } from '../testUtils';

jest.mock('../components/llm/ProviderWizardModal', () => ({
  __esModule: true,
  default: () => null,
}))
jest.mock('../components/llm/ModelSetDrawer', () => ({
  __esModule: true,
  default: () => null,
}))

jest.mock('../hooks/usePermission', () => ({
  usePermission: jest.fn(() => ({
    hasPermission: () => false,
    isPlatformAdmin: false,
    role: 'viewer',
    isAdmin: false,
    permissions: [],
    permissionsReady: true,
    filteredMenus: [],
  })),
}))

jest.mock('../services/llm', () => ({
  fetchLlmProviders: jest.fn().mockResolvedValue([
    { id: 1, name: '主用', provider_type: 'anthropic', base_url: 'https://api.anthropic.com',
      model: 'claude-sonnet-4-6', enabled: true, is_active: true, api_key_masked: 'sk-***' },
  ]),
  fetchActiveLlmProvider: jest.fn().mockResolvedValue(
    { id: 1, name: '主用', model: 'claude-sonnet-4-6', is_active: true, enabled: true },
  ),
  getPlatformPresets: jest.fn().mockResolvedValue([
    { name: 'Anthropic Claude', protocol: 'anthropic', base_url: 'https://api.anthropic.com', requires_key: true },
    { name: 'Ollama（本地）', protocol: 'openai_compatible', base_url: 'http://localhost:11434/v1', requires_key: false },
  ]),
  createLlmProvider: jest.fn(),
  updateLlmProvider: jest.fn(),
  deleteLlmProvider: jest.fn(),
  activateLlmProvider: jest.fn(),
  testLlmProvider: jest.fn(),
  probeModels: jest.fn(),
  probeTest: jest.fn(),
  getLlmProviderModels: jest.fn().mockResolvedValue([
    { model_id: 'claude-sonnet-4-6', alias: '', model_tier: 'strong', priority: 10, is_default: true, enabled: true, health_status: 'healthy' },
    { model_id: 'claude-haiku-4-5', alias: '', model_tier: 'basic', priority: 50, is_default: false, enabled: true, health_status: 'unknown' },
  ]),
  putLlmProviderModels: jest.fn(),
  fetchModelsDiff: jest.fn(),
  testLlmProviderModel: jest.fn(),
}));

import LlmProviders from './LlmProviders';
import { usePermission } from '../hooks/usePermission';
import { fetchLlmProviders, testLlmProvider } from '../services/llm';

const mockedPerm = usePermission as jest.Mock

test('renders provider list with protocol display name and readonly guard', async () => {
  render(withQuery(<LlmProviders />));
  expect(await screen.findByText('主用')).toBeInTheDocument();
  expect(screen.getByText('Anthropic 原生')).toBeInTheDocument(); // 协议显示名（不再是裸枚举值）
  expect(screen.getByText(/当前账号不能管理供应商/)).toBeInTheDocument();
  expect(screen.queryByText('新建供应商')).toBeNull();
  expect(screen.queryByText('管理模型')).toBeNull();
  expect(screen.queryByText('测试连接')).toBeNull();
});

test('tenant admin sees own-row write, hides platform-row write (GWT-06.5)', async () => {
  mockedPerm.mockReturnValue({
    hasPermission: (c: string) => c === 'btn:create' || c === 'btn:delete',
    isPlatformAdmin: false,
    role: 'admin',
    isAdmin: true,
    permissions: ['btn:create', 'btn:delete'],
    permissionsReady: true,
    filteredMenus: [],
  })
  ;(fetchLlmProviders as jest.Mock).mockResolvedValue([
    { id: 1, name: '本企业', provider_type: 'anthropic', base_url: 'https://api.anthropic.com',
      model: 'claude-sonnet-4-6', enabled: true, is_active: true, tenant_id: 9, api_key_masked: '***abcd' },
    { id: 2, name: '平台公共', provider_type: 'openai_compatible', base_url: 'https://platform.example/v1',
      model: 'm-pub', enabled: true, is_active: false, tenant_id: null, api_key_masked: '***zzzz' },
  ])
  render(withQuery(<LlmProviders />));
  expect(await screen.findByText('本企业')).toBeInTheDocument();
  expect(screen.getByText('平台公共')).toBeInTheDocument();
  expect(screen.getByText('平台')).toBeInTheDocument();
  expect(screen.getByText('新建供应商')).toBeInTheDocument();
  expect(screen.getAllByText('测试连接')).toHaveLength(1)
});

test('operator sees save and 测试连接 on own row (GWT-73.4 click)', async () => {
  mockedPerm.mockReturnValue({
    hasPermission: (c: string) => c === 'btn:create' || c === 'menu:llm',
    isPlatformAdmin: false,
    role: 'operator',
    isAdmin: false,
    permissions: ['btn:create', 'menu:llm'],
    permissionsReady: true,
    filteredMenus: [],
  })
  ;(fetchLlmProviders as jest.Mock).mockResolvedValue([
    { id: 1, name: '本企业', provider_type: 'anthropic', base_url: 'https://api.anthropic.com',
      model: 'claude-sonnet-4-6', enabled: true, is_active: true, tenant_id: 9, api_key_masked: '***abcd' },
    { id: 2, name: '平台公共', provider_type: 'openai_compatible', base_url: 'https://platform.example/v1',
      model: 'm-pub', enabled: true, is_active: false, tenant_id: null, api_key_masked: '***zzzz' },
  ])
  render(withQuery(<LlmProviders />));
  expect(await screen.findByText('本企业')).toBeInTheDocument();
  expect(screen.getByText('LLM 配置')).toBeInTheDocument();
  expect(screen.getByText('新建供应商')).toBeInTheDocument();
  expect(screen.queryByText(/当前账号不能管理供应商/)).toBeNull();
  expect(screen.getAllByText('测试连接')).toHaveLength(1);
});

test('operator click 测试连接 probes own-row id; fail copy is 本企业行 (GWT-73.4)', async () => {
  mockedPerm.mockReturnValue({
    hasPermission: (c: string) => c === 'btn:create' || c === 'menu:llm',
    isPlatformAdmin: false,
    role: 'operator',
    isAdmin: false,
    permissions: ['btn:create', 'menu:llm'],
    permissionsReady: true,
    filteredMenus: [],
  })
  ;(fetchLlmProviders as jest.Mock).mockResolvedValue([
    { id: 1, name: '本企业', provider_type: 'anthropic', base_url: 'https://api.anthropic.com',
      model: 'claude-sonnet-4-6', enabled: true, is_active: true, tenant_id: 9, api_key_masked: '***abcd' },
    { id: 2, name: '平台公共', provider_type: 'openai_compatible', base_url: 'https://platform.example/v1',
      model: 'm-pub', enabled: true, is_active: false, tenant_id: null, api_key_masked: '***zzzz' },
  ])
  ;(testLlmProvider as jest.Mock).mockResolvedValue({
    ok: false, error: '该行地址无响应', latency_ms: null, model: null,
  })
  render(withQuery(<LlmProviders />));
  expect(await screen.findByText('本企业')).toBeInTheDocument();
  fireEvent.click(screen.getByText('测试连接'));
  await waitFor(() => expect(testLlmProvider).toHaveBeenCalledWith(1));
  expect(testLlmProvider).not.toHaveBeenCalledWith(2);
  fireEvent.mouseEnter(await screen.findByText('失败'));
  await waitFor(() => {
    expect(document.body.textContent || '').toContain('连的是本企业供应商「本企业」')
  })
  const failCopy = document.body.textContent || ''
  expect(failCopy).toContain('不是平台网关')
  expect(failCopy).not.toContain('还没有平台模型')
  expect(failCopy).not.toContain('平台 LLM 网关不可达')
  expect(failCopy).not.toContain('暂无渠道')
});
