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

export interface PipelineProxyInfo {
  host: string
  port: number
  type: string
  protocol: string
  country: string
}

export interface PipelineStatus {
  identity_id: string
  // Captured at pipeline start so this record stays self-describing even
  // after a failed pipeline deletes the identity itself - the failure and
  // whose it was both stay visible on the Pipelines/Monitoring pages either way.
  display_name: string | null
  provider: string
  // 'queued' = created and handed to the pipeline scheduler, waiting for one
  // of its slots. Everything else is a run that has actually started.
  status: 'queued' | 'running' | 'waiting_manual' | 'completed' | 'failed'
  step_index: number
  step_name: string | null
  manual: boolean
  steps: { name: string; manual: boolean }[]
  proxy: PipelineProxyInfo | null
  error: string | null
  email: string | null
  // Raw Playwright/pipeline log lines (timestamp-prefixed), most recent
  // capped at MAX_LOG_LINES server-side - what the Monitoring page's
  // pipeline log viewer renders.
  logs: string[]
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

// What the backend's pipeline scheduler is doing with the identities it's been
// handed. Creating an identity that needs a mailbox queues it there; the
// scheduler assigns it a proxy and runs at most `concurrency` pipelines at once.
export interface PipelineQueueStatus {
  running: boolean
  queued: number
  active_slots: number
  concurrency: number
  // True when the scheduler also generates its own identities to keep every
  // slot busy, rather than only running what it's given.
  continuous: boolean
  launched: number
}

export const getPipelineQueue = async () => {
  const { data } = await api.get<PipelineQueueStatus>('/api/identities/pipeline-queue')
  return data
}

export const clearPipelineQueue = async () => {
  const { data } = await api.delete<{ dropped: number }>('/api/identities/pipeline-queue')
  return data
}
