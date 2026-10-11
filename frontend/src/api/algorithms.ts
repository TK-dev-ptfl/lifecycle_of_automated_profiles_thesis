import { api } from './client'

export interface MethodFile {
  name: string
  path: string
  content: string
}

export type MethodFilesResponse = Record<string, MethodFile[]>

export const getMethodFiles = async () => {
  const { data } = await api.get<MethodFilesResponse>('/api/algorithms/method-files')
  return data
}


// --- Behaviour runs ----------------------------------------------------------
//
// Running an algorithm from the dashboard. A run opens a real browser on the
// machine hosting the backend, so starting one returns immediately (202) and the
// client polls the run for progress.

export interface BehaviourScenario {
  key: string
  name: string
  description: string
  url: string
  fields: string[]
}

export interface BehaviourScoreRow {
  value?: string
  detail?: string
}

export interface BehaviourCheck {
  state: 'pass' | 'warn' | 'fail' | 'pending' | 'skip'
  name: string
  detail: string
  // Which of the page's detail tabs it came from: behaviour or fingerprint.
  group?: 'beh' | 'fp'
}

// The machine and browser the identity presented, derived from the same key as
// the persona (backend: app.behaviour.fingerprint).
export interface BehaviourFingerprint {
  browser?: string
  os?: string
  screen?: string
  viewport?: string
  gpu?: string
  cores?: number
  memory_gb?: number
  languages?: string[]
  timezone?: string
  user_agent?: string
}

export interface BehaviourScore {
  overall?: string
  verdict?: string
  behaviour?: BehaviourScoreRow
  fingerprint?: BehaviourScoreRow
  recaptcha?: BehaviourScoreRow
  checks?: BehaviourCheck[]
}

export interface BehaviourRun {
  id: string
  scenario: string
  identity: string
  url: string
  want: number
  headless: boolean
  show_cursor?: boolean
  status: 'running' | 'completed' | 'failed'
  // The persona the identity key derived to - typing speed, hesitancy, aim.
  profile: Record<string, unknown>
  fingerprint: BehaviourFingerprint
  logs: string[]
  items: Record<string, string>[]
  score: BehaviourScore | null
  error: string | null
  started_at: string
  finished_at: string | null
  elapsed_s: number
}

export const getBehaviourScenarios = async () => {
  const { data } = await api.get<BehaviourScenario[]>('/api/algorithms/behaviour-scenarios')
  return data
}

export const getBehaviourRuns = async (limit = 10) => {
  const { data } = await api.get<BehaviourRun[]>('/api/algorithms/behaviour-runs', { params: { limit } })
  return data
}

export const getBehaviourRun = async (id: string) => {
  const { data } = await api.get<BehaviourRun>(`/api/algorithms/behaviour-runs/${id}`)
  return data
}

export const startBehaviourRun = async (payload: {
  scenario: string
  identity: string
  want: number
  headless: boolean
  show_cursor?: boolean
  url?: string
}) => {
  const { data } = await api.post<BehaviourRun>('/api/algorithms/behaviour-runs', payload)
  return data
}
