import { create } from 'zustand'
import { createJSONStorage, persist, type StateStorage } from 'zustand/middleware'
import { login as apiLogin, logoutSession, LoginParams, LoginResponse } from '../services/auth'

interface AuthState {
  token: string | null
  /** 刷新令牌（决策 D10）：访问令牌过期时静默换新；随「记住我」存 local / session */
  refreshToken: string | null
  user: LoginResponse | null
  isAuthenticated: boolean
  rememberMe: boolean
  login: (params: LoginParams & { rememberMe?: boolean }) => Promise<void>
  setTokens: (token: string, refreshToken: string | null) => void
  logout: () => void
}

const safe = <T,>(fn: () => T, fallback: T): T => {
  try {
    return fn()
  } catch {
    return fallback
  }
}

/**
 * 会话存储（审计 BUG-07）：勾选「记住我」写 localStorage（跨浏览器重启保留），
 * 不勾选写 sessionStorage（刷新保留、关标签页即失效）。
 * 原先不勾选时什么都不持久化，刷新页面就被登出。
 */
export const sessionAwareStorage: StateStorage = {
  getItem: (name) =>
    safe(() => window.localStorage.getItem(name), null)
    ?? safe(() => window.sessionStorage.getItem(name), null),
  setItem: (name, value) => {
    const remember = safe(() => Boolean(JSON.parse(value)?.state?.rememberMe), false)
    safe(() => (remember ? window.localStorage : window.sessionStorage).setItem(name, value), undefined)
    safe(() => (remember ? window.sessionStorage : window.localStorage).removeItem(name), undefined)
  },
  removeItem: (name) => {
    safe(() => window.localStorage.removeItem(name), undefined)
    safe(() => window.sessionStorage.removeItem(name), undefined)
  },
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      refreshToken: null,
      user: null,
      isAuthenticated: false,
      rememberMe: false,
      login: async (params) => {
        const { rememberMe, ...loginParams } = params
        // 决策 D10：「记住我」决定刷新令牌窗口（7 天 / 按会话），要传给后端
        const data = await apiLogin({ ...loginParams, remember_me: !!rememberMe })
        // 审计 BUG-08：先写令牌再拉权限。原先顺序相反，/auth/permissions 不带令牌返回 401，
        // 触发全局登出回调，刚登录就被踢回登录页
        set({
          token: data.access_token,
          refreshToken: data.refresh_token ?? null,
          user: data,
          isAuthenticated: true,
          rememberMe: !!rememberMe,
        })
        // R5：登录即拉取权限单真相源缓存（后端 _ROLE_PERMISSIONS 下发）
        try {
          const { refreshPermissions } = await import('../hooks/usePermission')
          await refreshPermissions()
        } catch { /* 权限拉取失败=空缓存（全只读安全侧），不阻断登录 */ }
      },
      setTokens: (token, refreshToken) => set({ token, refreshToken }),
      logout: () => {
        // 服务端作废本会话的刷新令牌（其它设备不受影响）；失败不挡本地登出
        const refreshToken = get().refreshToken
        if (refreshToken) {
          logoutSession(refreshToken).catch(() => undefined)
        }
        // 权限缓存随登录态失效（防跨账号残留；下次 login 重新拉取）
        import('../hooks/usePermission').then(({ clearCachedPermissions }) =>
          clearCachedPermissions())
        // 查询缓存一并清空：上一个账号的列表 / 用量不能在下一个账号登录后闪现
        import('../queryClient').then(({ queryClient }) => queryClient.clear()).catch(() => undefined)
        set({ token: null, refreshToken: null, user: null, isAuthenticated: false, rememberMe: false })
      },
    }),
    {
      name: 'auth-storage',
      storage: createJSONStorage(() => sessionAwareStorage),
      partialize: (state: AuthState) => ({
        token: state.token,
        refreshToken: state.refreshToken,
        user: state.user,
        isAuthenticated: state.isAuthenticated,
        rememberMe: state.rememberMe,
      }),
    }
  )
)
