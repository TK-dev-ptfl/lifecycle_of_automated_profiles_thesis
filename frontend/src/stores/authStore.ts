import { create } from 'zustand'
import { login as apiLogin, logout as apiLogout } from '../api/auth'

interface AuthState {
  isAuthenticated: boolean
  username: string | null
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  isAuthenticated: !!localStorage.getItem('access_token'),
  username: localStorage.getItem('username'),

  login: async (username, password) => {
    const data = await apiLogin(username, password)
    localStorage.setItem('access_token', data.access_token)
    localStorage.setItem('refresh_token', data.refresh_token)
    localStorage.setItem('username', username)
    set({ isAuthenticated: true, username })
  },

  logout: () => {
    apiLogout().catch(() => {})
    localStorage.clear()
    set({ isAuthenticated: false, username: null })
  },
}))
