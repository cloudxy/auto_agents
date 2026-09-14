/**
 * T-34 / FR-99（§0.10 页头规范）系统设置页 UI 面：
 * - GWT-99.1 页名「系统设置」唯一标题在顶栏：页内无「全局系统设置」标题卡（复述页名），
 *   内容区表单分区直接开始
 * - GWT-99.3/99.4 动作与信息不丢：「保存并发布」「保存渠道配置」保留，
 *   原 Card extra 提示「修改后立即生效」移为表单上方说明行；区块标题（不复述页名）保留
 *
 * T-21 / FR-90（QA-22 并案：90.2 单 Then）：
 * - GWT-90.1 保存官网副标题类字段 → 成功句只声明保存；无「官网已同步」「官网内容已实时同步更新」
 *   （message.info 是旧已同步句的载体，必须零调用）；保存路径不发任何官网数据请求
 * - GWT-90.2（IMPL-QA-2 写面收紧后）非平台超管打开（租户 owner/admin/operator/viewer 统一）
 *   → 「当前账号不能改系统设置」说明态；无保存控件；**不是** 404 同形
 *   （后端 PUT /configs=require_platform_admin：给租户 owner/admin 表单是「见表单但保存必 403」）
 * - GWT-90.3 只读保存不可达：说明态无 form 元素（强提交不可达）+ 写 API 零调用
 *
 * mock 边界：services 层（settings/users）+ useAuthStore 容器夹具（Members.test 同款）。
 */
import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

jest.mock('../services/settings', () => ({
  fetchSiteConfigs: jest.fn().mockResolvedValue({}),
  fetchWebhookStatus: jest.fn().mockResolvedValue({ secret_configured: false, env_override_active: false }),
  updateSiteConfig: jest.fn().mockResolvedValue(undefined),
}))
jest.mock('../services/users', () => ({
  fetchNotifyConfig: jest.fn().mockResolvedValue({}),
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
import { updateSiteConfig } from '../services/settings'

const PLATFORM_ADMIN_USER = { tenant_role: null, is_platform_admin: true }
const OWNER_USER = { tenant_role: 'owner', is_platform_admin: false }
const ADMIN_USER = { tenant_role: 'admin', is_platform_admin: false }
const OPERATOR_USER = { tenant_role: 'operator', is_platform_admin: false }
const VIEWER_USER = { tenant_role: 'viewer', is_platform_admin: false }

beforeEach(() => {
  (message.error as jest.Mock).mockClear();
  (message.success as jest.Mock).mockClear();
  (message.info as jest.Mock).mockClear();
  (updateSiteConfig as jest.Mock).mockClear();
  // IMPL-QA-2 后唯一写者 = 平台超管：T-34/GWT-90.1 表单用例零逻辑改动保持绿
  mockUserState.current = PLATFORM_ADMIN_USER;
});

test('页头规范：无复述页名的标题卡，表单直接开始，动作与提示不丢（GWT-99.1/99.3/99.4）', async () => {
  render(<Settings />)
  // 保存动作在场（等待首屏 fetch 完成后表单渲染）
  expect(await screen.findByRole('button', { name: /保存并发布/ })).toBeInTheDocument()
  // 页名唯一标题在顶栏：原首 Card title「全局系统设置」不在场
  expect(screen.queryByText('全局系统设置')).toBeNull()
  // 内容区第一屏即表单分区；区块标题（§0.10 允许）与提示信息保留
  expect(screen.getByText('修改后立即生效')).toBeInTheDocument()
  expect(screen.getByText('Webhook 与通知渠道')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /保存渠道配置/ })).toBeInTheDocument()
})

describe('T-21 FR-90 设置页不得声称官网已同步', () => {
  test('GWT-90.1 保存官网副标题类字段：成功句只声明保存，无任何已同步句', async () => {
    render(<Settings />)
    expect(await screen.findByRole('button', { name: /保存并发布/ })).toBeInTheDocument()
    // 改「平台简介/SEO 描述」（官网 Hero 副标题类字段）后保存
    fireEvent.change(screen.getByPlaceholderText(/请描述该平台的主要功能/), {
      target: { value: '全新副标题文案' },
    })
    fireEvent.click(screen.getByRole('button', { name: /保存并发布/ }))
    // 保存动作真实发生（/configs 写）；页面不发出任何官网数据请求（mock 边界内只有 settings/users 服务）
    await waitFor(() => expect(updateSiteConfig).toHaveBeenCalled())
    // 成功句在场且只声明保存（edge-states 钦定「系统配置已保存」）
    await waitFor(() => expect((message.success as jest.Mock).mock.calls.length).toBeGreaterThan(0))
    const successCopy = (message.success as jest.Mock).mock.calls.map((c) => c.join('')).join('\n')
    expect(successCopy).toContain('已保存')
    // 禁句：不出现「官网」「同步」；message.info 是旧已同步句的载体，必须零调用
    expect(successCopy).not.toMatch(/官网|同步/)
    expect((message.info as jest.Mock)).not.toHaveBeenCalled()
  })

  test('GWT-M33 tenant operator 直打设置写面 is 404 same-shape, no form, no 只读说明态', async () => {
    mockUserState.current = OPERATOR_USER
    render(<MemoryRouter><Settings /></MemoryRouter>)
    expect(await screen.findByText('页面不存在或已被移除')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /返回工作台/ })).toBeInTheDocument()
    expect(screen.queryByText('当前账号不能改系统设置')).toBeNull()
    expect(screen.queryByRole('button', { name: /保存并发布/ })).toBeNull()
    expect(screen.queryByLabelText(/网站\/平台名称/)).toBeNull()
    expect(document.body.textContent || '').not.toMatch(/同步/)
  })

  test('GWT-M33 viewer 直打设置写面 is 404 same-shape, write API zero', async () => {
    mockUserState.current = VIEWER_USER
    render(<MemoryRouter><Settings /></MemoryRouter>)
    expect(await screen.findByText('页面不存在或已被移除')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /保存并发布/ })).toBeNull()
    expect(document.querySelector('form')).toBeNull()
    expect((updateSiteConfig as jest.Mock)).not.toHaveBeenCalled()
    expect((message.success as jest.Mock)).not.toHaveBeenCalled()
  })

  test('GWT-M33 tenant owner/admin 直打设置写面 is 404 same-shape', async () => {
    for (const formerWriter of [OWNER_USER, ADMIN_USER]) {
      mockUserState.current = formerWriter
      const { unmount } = render(<MemoryRouter><Settings /></MemoryRouter>)
      expect(await screen.findByText('页面不存在或已被移除')).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /保存并发布/ })).toBeNull()
      expect(screen.queryByText('当前账号不能改系统设置')).toBeNull()
      expect((updateSiteConfig as jest.Mock)).not.toHaveBeenCalled()
      unmount()
    }
  })

  test('写侧不回归：平台超管（后端 PUT /configs 守卫的角色）仍见表单与保存', async () => {
    mockUserState.current = PLATFORM_ADMIN_USER
    render(<Settings />)
    expect(await screen.findByRole('button', { name: /保存并发布/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /保存渠道配置/ })).toBeInTheDocument()
    expect(screen.queryByText('当前账号不能改系统设置')).toBeNull()
  })
})
