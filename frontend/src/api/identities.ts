import { api } from './client'
import type { Identity } from '../types'

export const getIdentities = async (params?: Record<string, string>) => {
  const { data } = await api.get<Identity[]>('/api/identities', { params })
  return data
}

export const generateIdentity = async (emailPlatformId: string) => {
  const { data } = await api.post<Identity>('/api/identities/generate', { email_platform_id: emailPlatformId })
  return data
}

export interface PipelineStatus {
  identity_id: string
  provider: string
  status: 'running' | 'waiting_manual' | 'completed' | 'failed'
  step_index: number
  step_name: string | null
  manual: boolean
  steps: { name: string; manual: boolean }[]
  error: string | null
  started_at: string
  updated_at: string
}

export const getAllPipelineStatus = async () => {
  const { data } = await api.get<PipelineStatus[]>('/api/identities/pipeline-status')
  return data
}

export const getPipelineStatus = async (identityId: string) => {
  const { data } = await api.get<PipelineStatus>(`/api/identities/${identityId}/pipeline-status`)
  return data
}

// Click target for "I solved the CAPTCHA - Continue": resumes a pipeline
// paused on its manual step instead of it waiting on backend terminal stdin.
export const continuePipeline = async (identityId: string) => {
  const { data } = await api.post<{ ok: boolean }>(`/api/identities/${identityId}/pipeline-status/continue`)
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
