/**
 * T-34 / FR-99（§0.10 页头规范）系统设置页 UI 面：
 * - GWT-99.1 页名「系统设置」唯一标题在顶栏：页内无「全局系统设置」标题卡（复述页名），
 *   内容区表单分区直接开始
 * - GWT-99.3/99.4 动作与信息不丢：保存动作与「保存渠道配置」保留，表单上方保留一行说明
 *
 * 审计 B5-2（P1-9）：页面只承诺已实现的能力——设置只落库，不同步官网 / 后台 Logo / SEO。
 * 说明行改为「仅保存配置，暂未同步到官网与后台」，按钮「保存」，tooltip 不再承诺官网与 SEO。
 *
 * 审计 BUG-37 / B5-3（P1-9）：三态加载
 * - 站点配置拉取失败：失败句 + 重试，**不渲染表单**（原先露出硬编码默认值，点保存会覆盖真实配置）
 * - 通知渠道 / Webhook 状态拉取失败：失败句 + 重试，不再永远转圈
 *
 * T-21 / FR-90（QA-22 并案：90.2 单 Then）：
 * - GWT-90.1 保存成功句只声明保存；无「官网已同步」类句子；保存路径不发官网数据请求
 * - GWT-M33 非平台超管打开 → 404 同形；无表单、写 API 零调用
 *
 * mock 边界：services 层（settings/users）+ useAuthStore 容器夹具（Members.test 同款）。
 */
import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { withQuery } from '../testUtils'

jest.mock('../services/settings', () => ({
  fetchSiteConfigs: jest.fn(),
  fetchWebhookStatus: jest.fn(),
  updateSiteConfig: jest.fn().mockResolvedValue(undefined),
}))
jest.mock('../services/users', () => ({
  fetchNotifyConfig: jest.fn(),
  updateNotifyConfig: jest.fn(),
}))

// babel-jest 工厂引用 mock* 前缀变量（render 时才读取，无 TDZ）——Members.test 同款
const mockUserState: { current: Record<string, unknown> | null } = { current: null };

jest.mock('../store/useAuthStore', () => ({
  useAuthStore: (sel: (s: { user: Record<string, unknown> | null }) => unknown) =>
    sel({ user: mockUserState.current }),
}));

jest.mock('antd', () => {
  const actual = jest.requireActual('antd');
  return {
    ...actual,
    message: {
      error: jest.fn(),
      success: jest.fn(),
      warning: jest.fn(),
      info: jest.fn(),
    },
  };
});

import { message } from 'antd'
import Settings from './Settings'
import { fetchSiteConfigs, fetchWebhookStatus, updateSiteConfig } from '../services/settings'
import { fetchNotifyConfig } from '../services/users'

const PLATFORM_ADMIN_USER = { tenant_role: null, is_platform_admin: true }
const OWNER_USER = { tenant_role: 'owner', is_platform_admin: false }
const ADMIN_USER = { tenant_role: 'admin', is_platform_admin: false }
const OPERATOR_USER = { tenant_role: 'operator', is_platform_admin: false }
const VIEWER_USER = { tenant_role: 'viewer', is_platform_admin: false }

const renderPage = () => render(withQuery(<MemoryRouter><Settings /></MemoryRouter>))

beforeEach(() => {
  (message.error as jest.Mock).mockClear();
  (message.success as jest.Mock).mockClear();
  (message.info as jest.Mock).mockClear();
  (updateSiteConfig as jest.Mock).mockClear();
  (fetchSiteConfigs as jest.Mock).mockReset().mockResolvedValue({ site_title: '真实平台名', site_description: '真实简介' });
  (fetchWebhookStatus as jest.Mock).mockReset().mockResolvedValue({ secret_configured: false, env_override_active: false });
  (fetchNotifyConfig as jest.Mock).mockReset().mockResolvedValue({});
  // IMPL-QA-2 后唯一写者 = 平台超管
  mockUserState.current = PLATFORM_ADMIN_USER;
});

test('页头规范：无复述页名的标题卡，表单直接开始，动作与说明不丢（GWT-99.1/99.3/99.4）', async () => {
  renderPage()
  expect(await screen.findByRole('button', { name: /^保\s*存$/ })).toBeInTheDocument()
  expect(screen.queryByText('全局系统设置')).toBeNull()
  expect(screen.getByText('仅保存配置，暂未同步到官网与后台')).toBeInTheDocument()
  expect(screen.getByText('Webhook 与通知渠道')).toBeInTheDocument()
  expect(await screen.findByRole('button', { name: /保存渠道配置/ })).toBeInTheDocument()
})

test('B5-2 页面不承诺未实现的同步：无「立即生效」「官网首页」「发布」', async () => {
  renderPage()
  await screen.findByRole('button', { name: /^保\s*存$/ })
  const text = document.body.textContent || ''
  expect(text).not.toMatch(/立即生效|官网首页|发布/)
})

test('加载成功：表单回填接口里的真实值（不是硬编码默认值）', async () => {
  renderPage()
  expect(await screen.findByDisplayValue('真实平台名')).toBeInTheDocument()
  expect(screen.getByDisplayValue('真实简介')).toBeInTheDocument()
})

test('BUG-37 站点配置加载失败：失败句 + 重试，不渲染表单、不可保存', async () => {
  (fetchSiteConfigs as jest.Mock).mockRejectedValue(new Error('network'))
  renderPage()
  expect(await screen.findByText('系统配置加载失败。检查网络后重试。')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /^保\s*存$/ })).toBeNull()
  expect(screen.queryByDisplayValue('AutoAgents')).toBeNull()
  expect(updateSiteConfig).not.toHaveBeenCalled()
  ;(fetchSiteConfigs as jest.Mock).mockResolvedValue({ site_title: '恢复后' })
  fireEvent.click(screen.getAllByRole('button', { name: /重\s*试/ })[0])
  expect(await screen.findByDisplayValue('恢复后')).toBeInTheDocument()
})

test('BUG-37 通知渠道 / Webhook 状态加载失败：失败句而不是永远转圈', async () => {
  (fetchNotifyConfig as jest.Mock).mockRejectedValue(new Error('network'));
  (fetchWebhookStatus as jest.Mock).mockRejectedValue(new Error('network'))
  renderPage()
  expect(await screen.findByText('通知渠道配置加载失败。检查网络后重试。')).toBeInTheDocument()
  expect(screen.getByText('Webhook 状态加载失败。检查网络后重试。')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /保存渠道配置/ })).toBeNull()
})

describe('T-21 FR-90 设置页不得声称官网已同步', () => {
  test('GWT-90.1 保存：成功句只声明保存，无任何已同步句', async () => {
    renderPage()
    await screen.findByDisplayValue('真实平台名')
    fireEvent.change(screen.getByPlaceholderText(/请描述该平台的主要功能/), {
      target: { value: '全新副标题文案' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^保\s*存$/ }))
    await waitFor(() => expect(updateSiteConfig).toHaveBeenCalledWith('site_description', '全新副标题文案'))
    await waitFor(() => expect((message.success as jest.Mock).mock.calls.length).toBeGreaterThan(0))
    const successCopy = (message.success as jest.Mock).mock.calls.map((c) => c.join('')).join('\n')
    expect(successCopy).toContain('已保存')
    expect(successCopy).not.toMatch(/官网|同步/)
    expect((message.info as jest.Mock)).not.toHaveBeenCalled()
  })

  test('GWT-M33 tenant operator 直打设置写面 is 404 same-shape, no form', async () => {
    mockUserState.current = OPERATOR_USER
    renderPage()
    expect(await screen.findByText('页面不存在或已被移除')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /返回工作台/ })).toBeInTheDocument()
    expect(screen.queryByText('当前账号不能改系统设置')).toBeNull()
    expect(screen.queryByLabelText(/网站\/平台名称/)).toBeNull()
    expect(fetchSiteConfigs).not.toHaveBeenCalled()
  })

  test('GWT-M33 viewer 直打设置写面 is 404 same-shape, write API zero', async () => {
    mockUserState.current = VIEWER_USER
    renderPage()
    expect(await screen.findByText('页面不存在或已被移除')).toBeInTheDocument()
    expect(document.querySelector('form')).toBeNull()
    expect((updateSiteConfig as jest.Mock)).not.toHaveBeenCalled()
    expect((message.success as jest.Mock)).not.toHaveBeenCalled()
  })

  test('GWT-M33 tenant owner/admin 直打设置写面 is 404 same-shape', async () => {
    for (const formerWriter of [OWNER_USER, ADMIN_USER]) {
      mockUserState.current = formerWriter
      const { unmount } = renderPage()
      expect(await screen.findByText('页面不存在或已被移除')).toBeInTheDocument()
      expect(screen.queryByText('当前账号不能改系统设置')).toBeNull()
      expect((updateSiteConfig as jest.Mock)).not.toHaveBeenCalled()
      unmount()
    }
  })
})
