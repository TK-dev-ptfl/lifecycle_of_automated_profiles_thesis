import { api } from './client'
import type { Identity } from '../types'

export const getIdentities = async (params?: Record<string, string>) => {
  const { data } = await api.get<Identity[]>('/api/identities', { params })
  return data
}

export const generateIdentity = async () => {
  const { data } = await api.post<Identity>('/api/identities/generate')
  return data
}

export const createIdentity = async (payload: Partial<Identity> & { password: string }) => {
  const { data } = await api.post<Identity>('/api/identities', payload)
  return data
}

export const updateIdentity = async (id: string, payload: Partial<Identity>) => {
  const { data } = await api.patch<Identity>(`/api/identities/${id}`, payload)
  return data
}

export const getIdentity = async (id: string) => {
  const { data } = await api.get<Identity>(`/api/identities/${id}`)
  return data
}

export const deleteIdentity = async (id: string) => api.delete(`/api/identities/${id}`)
