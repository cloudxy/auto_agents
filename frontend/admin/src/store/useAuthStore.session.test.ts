/**
 * 会话存储与登录顺序（审计 BUG-07 / BUG-08 回归）
 * - 不勾选「记住我」：写 sessionStorage（刷新不掉线），不写 localStorage
 * - 勾选：写 localStorage，并清掉 sessionStorage 里的旧副本
 * - 登录时先写令牌再拉权限（原先先拉权限 → 401 → 全局登出）
 */
jest.mock('../services/auth', () => ({
  login: jest.fn(),
  logoutSession: jest.fn().mockResolvedValue(undefined),
}))

const mockRefreshPermissions = jest.fn()
jest.mock('../hooks/usePermission', () => ({
  refreshPermissions: (...args: unknown[]) => mockRefreshPermissions(...args),
  clearCachedPermissions: jest.fn(),
}))

import { login as apiLogin, logoutSession } from '../services/auth'
import { sessionAwareStorage, useAuthStore } from './useAuthStore'

const STATE = (remember: boolean) => JSON.stringify({ state: { token: 't', rememberMe: remember }, version: 0 })

beforeEach(() => {
  window.localStorage.clear()
  window.sessionStorage.clear()
  mockRefreshPermissions.mockReset()
})

test('BUG-07 not remembered → sessionStorage only', () => {
  sessionAwareStorage.setItem('auth-storage', STATE(false))
  expect(window.sessionStorage.getItem('auth-storage')).not.toBeNull()
  expect(window.localStorage.getItem('auth-storage')).toBeNull()
  expect(sessionAwareStorage.getItem('auth-storage')).toContain('"token":"t"')
})

test('BUG-07 remembered → localStorage, session copy dropped', () => {
  sessionAwareStorage.setItem('auth-storage', STATE(false))
  sessionAwareStorage.setItem('auth-storage', STATE(true))
  expect(window.localStorage.getItem('auth-storage')).not.toBeNull()
  expect(window.sessionStorage.getItem('auth-storage')).toBeNull()
})

test('removeItem clears both stores', () => {
  window.localStorage.setItem('auth-storage', STATE(true))
  window.sessionStorage.setItem('auth-storage', STATE(false))
  sessionAwareStorage.removeItem('auth-storage')
  expect(window.localStorage.getItem('auth-storage')).toBeNull()
  expect(window.sessionStorage.getItem('auth-storage')).toBeNull()
})

test('BUG-08 token is stored before permissions are fetched', async () => {
  ;(apiLogin as jest.Mock).mockResolvedValue({ access_token: 'tok-1', username: 'a' })
  let tokenSeenByPermissions: string | null = null
  mockRefreshPermissions.mockImplementation(async () => {
    tokenSeenByPermissions = useAuthStore.getState().token
    return []
  })
  await useAuthStore.getState().login({ username: 'a', password: 'p' })
  expect(tokenSeenByPermissions).toBe('tok-1')
})

test('D10 login sends remember_me and keeps the refresh token; logout revokes it server-side', async () => {
  ;(apiLogin as jest.Mock).mockResolvedValue({ access_token: 'tok-2', refresh_token: 'rt-2', username: 'a' })
  mockRefreshPermissions.mockResolvedValue([])
  await useAuthStore.getState().login({ username: 'a', password: 'p', rememberMe: true })
  expect(apiLogin).toHaveBeenCalledWith({ username: 'a', password: 'p', remember_me: true })
  expect(useAuthStore.getState().refreshToken).toBe('rt-2')
  useAuthStore.getState().logout()
  expect(logoutSession).toHaveBeenCalledWith('rt-2')
  expect(useAuthStore.getState().refreshToken).toBeNull()
  expect(useAuthStore.getState().token).toBeNull()
})

test('D10 setTokens swaps both tokens after a silent refresh', () => {
  useAuthStore.getState().setTokens('acc-3', 'rt-3')
  expect(useAuthStore.getState().token).toBe('acc-3')
  expect(useAuthStore.getState().refreshToken).toBe('rt-3')
})
