import { api } from './client'
import type { Platform, FleetSummary, FleetHealthItem } from '../types'

export const getPlatforms = async () => {
  return [
    {
      id: 'a0000000-0000-0000-0000-000000000001',
      name: 'reddit',
      display_name: 'Reddit',
      is_enabled: true,
      rate_limits: {},
      adapter_config: {},
      created_at: new Date().toISOString(),
    },
  ] as Platform[]
}

export const createPlatform = async (payload: Partial<Platform>) => {
  return {
    id: 'a0000000-0000-0000-0000-000000000001',
    name: 'reddit',
    display_name: 'Reddit',
    is_enabled: true,
    rate_limits: payload.rate_limits ?? {},
    adapter_config: payload.adapter_config ?? {},
    created_at: new Date().toISOString(),
  } as Platform
}

export const updatePlatform = async (id: string, payload: Partial<Platform>) => {
  return {
    id: 'a0000000-0000-0000-0000-000000000001',
    name: 'reddit',
    display_name: 'Reddit',
    is_enabled: payload.is_enabled ?? true,
    rate_limits: payload.rate_limits ?? {},
    adapter_config: payload.adapter_config ?? {},
    created_at: new Date().toISOString(),
  } as Platform
}

export const getFleetSummary = async () => {
  const { data } = await api.get<FleetSummary>('/api/fleet/summary')
  return data
}

export const getFleetHealth = async () => {
  const { data } = await api.get<FleetHealthItem[]>('/api/fleet/health')
  return data
}
