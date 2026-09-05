/**
 * LLM 供应商页 smoke（工单 24）：只读态渲染列表壳；管理模型入口在只读态隐藏。
 */
import React from 'react';
import { render, screen } from '@testing-library/react';

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

test('renders provider list with protocol display name and readonly guard', async () => {
  render(<LlmProviders />);
  expect(await screen.findByText('主用')).toBeInTheDocument();
  expect(screen.getByText('Anthropic 原生')).toBeInTheDocument(); // 协议显示名（不再是裸枚举值）
  expect(screen.getByText(/仅管理员可管理供应商/)).toBeInTheDocument(); // 默认 viewer 只读
  expect(screen.queryByText('新建供应商')).toBeNull();
  expect(screen.queryByText('管理模型')).toBeNull();
});
