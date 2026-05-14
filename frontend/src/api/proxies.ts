import { api } from './client'
import type { Proxy } from '../types'

export const getProxy = async (id: string) => {
  const { data } = await api.get<Proxy>(`/api/proxies/${id}`)
  return data
}

export const getProxies = async (params?: Record<string, string>) => {
  const { data } = await api.get<Proxy[]>('/api/proxies', { params })
  return data
}

export const createProxy = async (payload: Partial<Proxy>) => {
  const { data } = await api.post<Proxy>('/api/proxies', payload)
  return data
}

export const deleteProxy = async (id: string) => api.delete(`/api/proxies/${id}`)

export const testProxy = async (id: string) => {
  const { data } = await api.post<Proxy>(`/api/proxies/${id}/test`)
  return data
}

export const testAllProxies = async () => api.post('/api/proxies/test-all')

export const cleanupUnhealthyProxies = async () => {
  const { data } = await api.post('/api/proxies/cleanup')
  return data
}

export const fetchProxiesFromFreeList = async () => {
  const { data } = await api.post('/api/proxies/fetch-from-free-list')
  return data
}

