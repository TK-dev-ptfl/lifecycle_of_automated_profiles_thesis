import { api } from './client'
import type { Platform, FleetSummary, FleetHealthItem } from '../types'

export const getPlatforms = async () => {
  const { data } = await api.get<Platform[]>('/api/platforms')
  return data
}

export const createPlatform = async (payload: Partial<Platform>) => {
  const { data } = await api.post<Platform>('/api/platforms', payload)
  return data
}

export const updatePlatform = async (id: string, payload: Partial<Platform>) => {
  const { data } = await api.patch<Platform>(`/api/platforms/${id}`, payload)
  return data
}

export const getFleetSummary = async () => {
  const { data } = await api.get<FleetSummary>('/api/fleet/summary')
  return data
}

export const getFleetHealth = async () => {
  const { data } = await api.get<FleetHealthItem[]>('/api/fleet/health')
  return data
}
