import { api } from './client'
import type { Bot, BotMode, BotStatus, BotStats, Log } from '../types'

export const getBots = async (params?: Record<string, string>) => {
  const { data } = await api.get<Bot[]>('/api/bots', { params })
  return data
}

export const getBot = async (id: string) => {
  const { data } = await api.get<Bot>(`/api/bots/${id}`)
  return data
}

export const createBot = async (payload: Partial<Bot>) => {
  const { data } = await api.post<Bot>('/api/bots', payload)
  return data
}

export const updateBot = async (id: string, payload: Partial<Bot>) => {
  const { data } = await api.patch<Bot>(`/api/bots/${id}`, payload)
  return data
}

export const deleteBot = async (id: string) => api.delete(`/api/bots/${id}`)

export const runBot = async (id: string) => {
  const { data } = await api.post<Bot>(`/api/bots/${id}/run`)
  return data
}

export const pauseBot = async (id: string) => {
  const { data } = await api.post<Bot>(`/api/bots/${id}/pause`)
  return data
}

export const stopBot = async (id: string) => {
  const { data } = await api.post<Bot>(`/api/bots/${id}/stop`)
  return data
}

export const setBotMode = async (id: string, mode: BotMode) => {
  const { data } = await api.post<Bot>(`/api/bots/${id}/set-mode`, { mode })
  return data
}

export const getBotLogs = async (id: string, skip = 0, limit = 50) => {
  const { data } = await api.get<Log[]>(`/api/bots/${id}/logs`, { params: { skip, limit } })
  return data
}

export const getBotStats = async (id: string) => {
  const { data } = await api.get<BotStats>(`/api/bots/${id}/stats`)
  return data
}

export const getBotFlags = async (id: string) => {
  const { data } = await api.get<Log[]>(`/api/bots/${id}/flags`)
  return data
}
