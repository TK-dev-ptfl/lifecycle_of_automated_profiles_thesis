export type BotStatus = 'running' | 'paused' | 'stopped' | 'flagged' | 'banned'
export type BotMode = 'growing' | 'trust' | 'executing' | 'maintaining'
export type CommunicationMode = 'official_api' | 'unofficial_api' | 'scraping' | 'human_emulation'
export type BehaviourPattern = 'passive' | 'reactive' | 'proactive' | 'aggressive'
export type IdentityStatus = 'fresh' | 'active' | 'flagged' | 'burned'
export type ProxyProtocol = 'http' | 'socks5'
export type ProxyType = 'residential' | 'datacenter' | 'mobile'
export type TaskType = 'scrape' | 'post' | 'engage' | 'monitor' | 'seed' | 'vote'
export type TaskStatus = 'idle' | 'running' | 'paused' | 'completed' | 'failed'
export type SyncMode = 'independent' | 'sharded' | 'coordinated'
export type LogLevel = 'info' | 'warn' | 'error' | 'flag'
export type LogCategory = 'action' | 'system' | 'network' | 'detection'

export interface Platform {
  id: string
  name: string
  display_name: string
  is_enabled: boolean
  rate_limits: Record<string, unknown>
  adapter_config: Record<string, unknown>
  created_at: string
}

export interface Identity {
  id: string
  display_name: string
  username: string
  email: string
  email_provider: string
  phone_number?: string
  phone_provider?: string
  profile_photo_url?: string
  bio?: string
  location: string
  age: number
  interests: string[]
  browser_profile_id: string
  browser_profile_provider: string
  status: IdentityStatus
  created_at: string
}

export interface Proxy {
  id: string
  host: string
  port: number
  username?: string
  protocol: ProxyProtocol
  type: ProxyType
  country: string
  city?: string
  provider: string
  assigned_bot_id?: string
  is_healthy: boolean
  last_checked: string
  created_at: string
}

export interface Bot {
  id: string
  name: string
  platform_id: string
  identity_id?: string
  password?: string
  proxy_id?: string
  skeleton: string
  mode: BotMode
  status: BotStatus
  communication_mode: CommunicationMode
  behaviour_pattern: BehaviourPattern
  parameters: Record<string, unknown>
  algorithm_config: Record<string, unknown>
  task_id?: string
  flag_count: number
  last_active: string
  created_at: string
  updated_at: string
}

export interface Task {
  id: string
  name: string
  platform_id: string
  type: TaskType
  status: TaskStatus
  payload: Record<string, unknown>
  schedule: Record<string, unknown>
  concurrency: number
  sync_mode: SyncMode
  success_criteria: Record<string, unknown>
  result_count: number
  error_count: number
  created_at: string
  started_at?: string
  completed_at?: string
}

export interface Log {
  id: string
  bot_id: string
  task_id?: string
  level: LogLevel
  category: LogCategory
  message: string
  metadata: Record<string, unknown>
  created_at: string
}

export interface BotStats {
  actions_today: number
  actions_lifetime: number
  success_rate: number
  uptime_hours: number
  flag_count: number
}

export interface FleetSummary {
  total: number
  by_status: Record<BotStatus, number>
  by_mode: Record<BotMode, number>
}

export interface FleetHealthItem {
  id: string
  name: string
  status: BotStatus
  mode: BotMode
  flag_count: number
  last_active: string
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export type EmailType = 'temporary' | 'own_mailserver' | 'classic'

export interface EmailPlatform {
  id: string
  type: EmailType
  name: string
  domain: string
  created_at: string
}

export interface EmailAccount {
  id: string
  type: EmailType
  provider_id: string
  address: string
  password?: string
  created_at: string
  used_by_bot_id: string | null
  ever_blocked: boolean
  blocked_on_platforms: string[]
}
