import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { login as apiLogin, LoginParams, LoginResponse } from '../services/auth'

interface AuthState {
  token: string | null
  user: LoginResponse | null
  isAuthenticated: boolean
  rememberMe: boolean
  login: (params: LoginParams & { rememberMe?: boolean }) => Promise<void>
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      isAuthenticated: false,
      rememberMe: false,
      login: async (params) => {
        const { rememberMe, ...loginParams } = params
        const data = await apiLogin(loginParams)
        // R5：登录即拉取权限单真相源缓存（后端 _ROLE_PERMISSIONS 下发）
        try {
          const { refreshPermissions } = await import('../hooks/usePermission')
          await refreshPermissions()
        } catch { /* 权限拉取失败=空缓存（全只读安全侧），不阻断登录 */ }
        set({ 
          token: data.access_token, 
          user: data, 
          isAuthenticated: true,
          rememberMe: !!rememberMe
        })
      },
      logout: () => {
        // 权限缓存随登录态失效（防跨账号残留；下次 login 重新拉取）
        import('../hooks/usePermission').then(({ clearCachedPermissions }) =>
          clearCachedPermissions())
        set({ token: null, user: null, isAuthenticated: false, rememberMe: false })
      },
    }),
    {
      name: 'auth-storage',
      partialize: (state: AuthState) => {
        if (!state.rememberMe && !state.token) return {} // If not remember me, we might want to clear on close, but zustand/persist is localStorage.
        return { 
          token: state.token, 
          user: state.user,
          isAuthenticated: state.isAuthenticated,
          rememberMe: state.rememberMe
        }
      },
    }
  )
)
