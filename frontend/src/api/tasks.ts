import { api } from './client'
import type { Task, Bot } from '../types'

export const getTasks = async () => {
  const { data } = await api.get<Task[]>('/api/tasks')
  return data
}

export const getTask = async (id: string) => {
  const { data } = await api.get<Task>(`/api/tasks/${id}`)
  return data
}

export const createTask = async (payload: Partial<Task>) => {
  const { data } = await api.post<Task>('/api/tasks', payload)
  return data
}

export const updateTask = async (id: string, payload: Partial<Task>) => {
  const { data } = await api.patch<Task>(`/api/tasks/${id}`, payload)
  return data
}

export const deleteTask = async (id: string) => api.delete(`/api/tasks/${id}`)

export const runTask = async (id: string) => {
  const { data } = await api.post<Task>(`/api/tasks/${id}/run`)
  return data
}

export const pauseTask = async (id: string) => {
  const { data } = await api.post<Task>(`/api/tasks/${id}/pause`)
  return data
}

export const stopTask = async (id: string) => {
  const { data } = await api.post<Task>(`/api/tasks/${id}/stop`)
  return data
}

export const getTaskBots = async (id: string) => {
  const { data } = await api.get<Bot[]>(`/api/tasks/${id}/bots`)
  return data
}

export const assignBots = async (taskId: string, botIds: string[]) => {
  const { data } = await api.post<Task>(`/api/tasks/${taskId}/assign`, { bot_ids: botIds })
  return data
}

export const unassignBots = async (taskId: string, botIds: string[]) => {
  const { data } = await api.post<Task>(`/api/tasks/${taskId}/unassign`, { bot_ids: botIds })
  return data
}
