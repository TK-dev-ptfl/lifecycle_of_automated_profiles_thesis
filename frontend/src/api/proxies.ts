import { api } from './client'
import type { Proxy } from '../types'

export const getProxy = async (id: string) => {
  const { data } = await api.get<Proxy>(`/api/proxies/${id}`)
  return data
}

// Pass retired: 'false' to hide proxies permanently out of circulation - ones a
// pipeline has used, or that were retired after failing in real use. Their rows
// are kept forever so a later scrape can't re-import the same address, so they
// accumulate into the thousands and swamp the list otherwise.
export const getProxies = async (params?: Record<string, string>) => {
  const { data } = await api.get<Proxy[]>('/api/proxies', { params })
  return data
}

export interface ProxyStats {
  total: number
  retired: number
  available: number
  available_healthy: number
}

export const getProxyStats = async () => {
  const { data } = await api.get<ProxyStats>('/api/proxies/stats')
  return data
}

export const createProxy = async (payload: Partial<Proxy>) => {
  const { data } = await api.post<Proxy>('/api/proxies', payload)
  return data
}

export const updateProxy = async (id: string, payload: Partial<Proxy>) => {
  const { data } = await api.patch<Proxy>(`/api/proxies/${id}`, payload)
  return data
}

export const deleteProxy = async (id: string) => api.delete(`/api/proxies/${id}`)

// claimFor, if given, is an identity id (typically generated client-side
// before the identity itself is created - see genId() in Identities/index.tsx)
// that this proxy gets atomically assigned to, server-side, the instant it's
// confirmed healthy - in the same request, not a separate later one. Without
// this, a proxy tested here sits fully unclaimed until some later call
// reserves it, and in between a different, already-running pipeline's own
// free-pool search could grab the exact same proxy first. Check the
// returned Proxy's assigned_bot_id against your own claimFor rather than
// just is_healthy - a concurrent claim can still legitimately win this race,
// same as anywhere else this pattern is used.
export const testProxy = async (id: string, claimFor?: string) => {
  const { data } = await api.post<Proxy>(`/api/proxies/${id}/test`, null, {
    params: claimFor ? { claim_for: claimFor } : undefined,
  })
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
