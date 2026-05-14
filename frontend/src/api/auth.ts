import { api } from './client'
import type { TokenResponse } from '../types'

export const login = async (username: string, password: string): Promise<TokenResponse> => {
  const form = new URLSearchParams({ username, password })
  const { data } = await api.post<TokenResponse>('/api/auth/login', form)
  return data
}

export const logout = async () => api.post('/api/auth/logout')
