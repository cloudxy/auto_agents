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
        set({ 
          token: data.access_token, 
          user: data, 
          isAuthenticated: true,
          rememberMe: !!rememberMe
        })
      },
      logout: () => {
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
