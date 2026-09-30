import { api } from './client'

// The two background loops in app/workers: the proxy refresher (replaces the
// free part of the proxy pool every 2 minutes) and the pipeline scheduler
// (keeps N email-creation pipelines in flight, starting a new one the moment
// one finishes). See app/workers/__init__.py for the split of responsibility.

export interface WorkerStatus {
  name: string
  running: boolean
  interval_s: number
  started_at: string | null
  last_run_at: string | null
  cycles: number
  last_error: string | null
  logs: string[]
  // proxy-refresher only
  last_result?: { removed?: number; imported?: number; skipped?: number; error?: string } | null
  // pipeline-scheduler only
  concurrency?: number
  // True when the scheduler also generates its own identities to keep every
  // slot busy; false when it only runs what's been queued to it.
  continuous?: boolean
  queued?: number
  active_slots?: number
  email_platform_id?: string | null
  launched?: number
  failed_to_launch?: number
  proxy_candidates_remaining?: number
  proxy_pool_refills?: number
}

export const PROXY_REFRESHER = 'proxy-refresher'
export const PIPELINE_SCHEDULER = 'pipeline-scheduler'

export const getWorkers = async () => {
  const { data } = await api.get<WorkerStatus[]>('/api/workers')
  return data
}

export const startProxyRefresher = async () => {
  const { data } = await api.post(`/api/workers/${PROXY_REFRESHER}/start`)
  return data
}

export const stopProxyRefresher = async () => {
  const { data } = await api.post(`/api/workers/${PROXY_REFRESHER}/stop`)
  return data
}

// Normally unnecessary - creating an identity that needs a mailbox queues it
// and starts this worker by itself. Call it to change the concurrency cap, or
// to turn on continuous mode, where the scheduler generates its own identities
// to keep every slot busy rather than only running what it's given. All three
// settings persist across a later stop/start.
export const startPipelineScheduler = async (payload?: {
  concurrency?: number
  email_platform_id?: string
  continuous?: boolean
}) => {
  const { data } = await api.post(`/api/workers/${PIPELINE_SCHEDULER}/start`, payload ?? {})
  return data
}

// Cancels the in-flight pipelines along with the supervisor - their browsers
// are closed rather than orphaned - and turns continuous mode off. Jobs already
// queued are kept; clear those with clearPipelineQueue.
export const stopPipelineScheduler = async () => {
  const { data } = await api.post(`/api/workers/${PIPELINE_SCHEDULER}/stop`)
  return data
}
