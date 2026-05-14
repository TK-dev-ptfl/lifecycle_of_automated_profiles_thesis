import { useState, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getBot, getBotStats, getBotLogs, getBotFlags, runBot, pauseBot, stopBot } from '../../api/bots'
import { getTask, getTaskBots } from '../../api/tasks'
import { getIdentity } from '../../api/identities'
import { getProxy } from '../../api/proxies'
import { Badge } from '../../components/ui/Badge'
import { StatusDot } from '../../components/ui/StatusDot'
import { Button } from '../../components/ui/Button'
import { KpiCard } from '../../components/ui/KpiCard'
import { DataTable, Column } from '../../components/ui/DataTable'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import type { Log } from '../../types'
import { format, formatDistanceToNow } from 'date-fns'
import { ALGORITHM_CATALOGUE, METHOD_LABELS, RESULT_COLOURS, type AlgorithmDef } from '../../data/algorithms'

// ─── Email from localStorage ──────────────────────────────────────────────────

interface EmailAccount { id: string; address: string; provider: string; type: string; ever_blocked: boolean; blocked_on_platforms: string[]; used_by_bot_id: string | null }
function getBotEmail(botId: string): EmailAccount | null {
  try {
    const all: EmailAccount[] = JSON.parse(localStorage.getItem('email_accounts') ?? '[]')
    return all.find(e => e.used_by_bot_id === botId) ?? null
  } catch { return null }
}

// ─── Payload ──────────────────────────────────────────────────────────────────

interface PayloadData { goal?: { description: string; topics: string[]; target_count: number }; method?: string; algorithm_id?: string }
function parsePl(raw: Record<string, unknown>): PayloadData {
  return { goal: raw.goal as PayloadData['goal'], method: raw.method as string, algorithm_id: raw.algorithm_id as string }
}

const mockChart = Array.from({ length: 7 }, (_, i) => ({
  day: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][i],
  actions: Math.floor(Math.random() * 120 + 10),
  errors: Math.floor(Math.random() * 8),
}))

// ─── Mode derivation ──────────────────────────────────────────────────────────

const modeVisuals = {
  running_task: { label: 'Running Task',      border: 'border-emerald-700/50', bg: 'bg-emerald-900/20', text: 'text-emerald-400', icon: '▶' },
  in_pipeline:  { label: 'In Pipeline',       border: 'border-brand-700/50',   bg: 'bg-brand-900/20',   text: 'text-brand-400',   icon: '⟳' },
  not_running:  { label: 'Not Running',       border: 'border-gray-700',       bg: 'bg-gray-800/40',    text: 'text-gray-400',    icon: '⏹' },
  blocked:      { label: 'Blocked / Flagged', border: 'border-red-700/50',     bg: 'bg-red-900/20',     text: 'text-red-400',     icon: '⚠' },
} as const

type ModeKey = keyof typeof modeVisuals

function deriveBotMode(status: string, taskId?: string | null): ModeKey {
  if (status === 'flagged' || status === 'banned') return 'blocked'
  if (status === 'running' && taskId) return 'running_task'
  if (status === 'running') return 'in_pipeline'
  return 'not_running'
}

// ─── Small reusable UI ────────────────────────────────────────────────────────

function InfoRow({ label, value, mono = false }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between py-2 border-b border-gray-700/30 last:border-0 gap-4">
      <span className="text-xs text-gray-500 shrink-0 w-32">{label}</span>
      <span className={`text-sm text-gray-200 text-right flex-1 ${mono ? 'font-mono' : ''}`}>{value}</span>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-gray-700/50 bg-gray-900/40 overflow-hidden">
      <div className="px-4 py-2.5 border-b border-gray-700/40">
        <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">{title}</p>
      </div>
      <div className="px-4 py-3">{children}</div>
    </div>
  )
}

function AlgChain({ alg }: { alg: AlgorithmDef }) {
  return (
    <div className="flex items-center gap-1.5 flex-wrap text-[10px] font-mono">
      <span className="text-gray-700">BaseAlgorithm</span>
      <span className="text-gray-700">→</span>
      <span className="text-gray-500">{alg.parent}</span>
      <span className="text-gray-700">→</span>
      <span className={`px-1.5 py-0.5 rounded font-semibold ${RESULT_COLOURS[alg.resultType]}`}>{alg.id}</span>
    </div>
  )
}

// ─── Lifecycle stage ──────────────────────────────────────────────────────────

type LifecycleStageKey = 'fresh' | 'warming' | 'active' | 'established' | 'at_risk' | 'burned'

const LC_STAGES: { key: LifecycleStageKey; label: string; desc: string; cls: string }[] = [
  { key: 'fresh',       label: 'Fresh',       desc: 'Newly created, not yet active',           cls: 'text-sky-400 border-sky-700/50 bg-sky-900/20'     },
  { key: 'warming',     label: 'Warming',     desc: 'Building activity history and trust',     cls: 'text-blue-400 border-blue-700/50 bg-blue-900/20'  },
  { key: 'active',      label: 'Active',      desc: 'Fully operational, healthy account',      cls: 'text-emerald-400 border-emerald-700/50 bg-emerald-900/20' },
  { key: 'established', label: 'Established', desc: 'Long-standing, high trust score',         cls: 'text-purple-400 border-purple-700/50 bg-purple-900/20'  },
  { key: 'at_risk',     label: 'At Risk',     desc: 'Flagged activity — reduce exposure',      cls: 'text-amber-400 border-amber-700/50 bg-amber-900/20'   },
  { key: 'burned',      label: 'Burned',      desc: 'Account compromised or banned',           cls: 'text-red-400 border-red-700/50 bg-red-900/20'     },
]

function deriveLifecycleStage(bot: { status: string; flag_count: number; created_at: string }): LifecycleStageKey {
  if (bot.status === 'banned') return 'burned'
  if (bot.flag_count >= 3) return 'at_risk'
  if (bot.status === 'flagged') return 'at_risk'
  const ageMs = Date.now() - new Date(bot.created_at).getTime()
  const ageDays = ageMs / 86400000
  if (ageDays >= 90 && bot.flag_count === 0) return 'established'
  if (ageDays >= 14) return 'active'
  if (ageDays >= 3) return 'warming'
  return 'fresh'
}

function LifecycleStage({ bot }: { bot: { status: string; flag_count: number; created_at: string } }) {
  const current = deriveLifecycleStage(bot)
  const currentIdx = LC_STAGES.findIndex(s => s.key === current)
  const stage = LC_STAGES[currentIdx]

  return (
    <div className="rounded-xl border border-gray-700/50 bg-gray-900/40 overflow-hidden">
      <div className="px-4 py-2.5 border-b border-gray-700/40 flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">Account lifecycle</p>
        <span className={`text-xs font-semibold px-2 py-0.5 rounded border ${stage.cls}`}>{stage.label}</span>
      </div>
      <div className="px-4 py-4">
        <div className="flex items-center gap-1 mb-3">
          {LC_STAGES.map((s, i) => {
            const isPast = i < currentIdx
            const isCurrent = i === currentIdx
            return (
              <div key={s.key} className="flex items-center gap-1 flex-1 min-w-0">
                <div className="flex-1 flex flex-col items-center gap-1">
                  <div className={`w-full h-1.5 rounded-full transition-colors ${isCurrent ? 'bg-brand-500' : isPast ? 'bg-gray-500' : 'bg-gray-700'}`} />
                  <span className={`text-[10px] truncate w-full text-center ${isCurrent ? 'text-gray-200 font-semibold' : isPast ? 'text-gray-500' : 'text-gray-700'}`}>
                    {s.label}
                  </span>
                </div>
              </div>
            )
          })}
        </div>
        <p className="text-xs text-gray-500">{stage.desc}</p>
      </div>
    </div>
  )
}

const TABS = [
  { id: 'overview',  label: 'Overview' },
  { id: 'task',      label: 'Task' },
  { id: 'resources', label: 'Resources' },
  { id: 'history',   label: 'History' },
  { id: 'logs',      label: 'Logs & Flags' },
]

// ─── Main ─────────────────────────────────────────────────────────────────────

export default function BotDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [tab, setTab] = useState('overview')

  const { data: bot, isLoading } = useQuery({ queryKey: ['bot', id], queryFn: () => getBot(id!) })
  const { data: stats } = useQuery({ queryKey: ['bot-stats', id], queryFn: () => getBotStats(id!), enabled: !!bot })
  const { data: logs = [] } = useQuery({ queryKey: ['bot-logs', id], queryFn: () => getBotLogs(id!), enabled: tab === 'logs' })
  const { data: flags = [] } = useQuery({ queryKey: ['bot-flags', id], queryFn: () => getBotFlags(id!), enabled: tab === 'logs' })
  const { data: task } = useQuery({ queryKey: ['task', bot?.task_id], queryFn: () => getTask(bot!.task_id!), enabled: !!bot?.task_id })
  const { data: taskBots = [] } = useQuery({ queryKey: ['task-bots-detail', bot?.task_id], queryFn: () => getTaskBots(bot!.task_id!), enabled: !!bot?.task_id })
  const { data: identity } = useQuery({ queryKey: ['identity', bot?.identity_id], queryFn: () => getIdentity(bot!.identity_id!), enabled: !!bot?.identity_id })
  const { data: proxy } = useQuery({ queryKey: ['proxy', bot?.proxy_id], queryFn: () => getProxy(bot!.proxy_id!), enabled: !!bot?.proxy_id })

  const email = useMemo(() => bot ? getBotEmail(bot.id) : null, [bot])

  const inv = () => qc.invalidateQueries({ queryKey: ['bot', id] })
  const run = useMutation({ mutationFn: () => runBot(id!), onSuccess: inv })
  const pause = useMutation({ mutationFn: () => pauseBot(id!), onSuccess: inv })
  const stop = useMutation({ mutationFn: () => stopBot(id!), onSuccess: inv })

  if (isLoading || !bot) return <div className="flex items-center justify-center h-64 text-gray-500">Loading…</div>

  const modeKey = deriveBotMode(bot.status, bot.task_id)
  const mv = modeVisuals[modeKey]

  const taskPayload = task ? parsePl(task.payload) : null
  const taskAlg = taskPayload?.algorithm_id ? ALGORITHM_CATALOGUE.find(a => a.id === taskPayload.algorithm_id) : null

  const logCols: Column<Log>[] = [
    { key: 't', header: 'Time',     render: l => <span className="text-xs text-gray-500">{format(new Date(l.created_at), 'HH:mm:ss')}</span> },
    { key: 'l', header: 'Level',    render: l => { const m: Record<string, 'success'|'warning'|'danger'|'gray'> = { info:'gray', warn:'warning', error:'danger', flag:'danger' }; return <Badge variant={m[l.level] ?? 'gray'} label={l.level} /> } },
    { key: 'c', header: 'Category', render: l => <span className="text-xs text-gray-500">{l.category}</span> },
    { key: 'm', header: 'Message',  render: l => <span className="text-sm text-gray-300">{l.message}</span> },
  ]

  return (
    <div className="space-y-4">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/fleet')} className="text-gray-500 hover:text-gray-300 text-sm transition-colors">← Fleet</button>
          <div className="h-4 w-px bg-gray-700" />
          <StatusDot status={bot.status} className="h-3 w-3" />
          <h2 className="text-lg font-semibold text-gray-100">{bot.name}</h2>
          <Badge variant={bot.status === 'running' ? 'success' : bot.status === 'flagged' ? 'danger' : bot.status === 'paused' ? 'warning' : 'gray'} label={bot.status} />
        </div>
        <div className="flex gap-2">
          {bot.status !== 'running' && <Button variant="success" onClick={() => run.mutate()} loading={run.isPending}>▶ Run</Button>}
          {bot.status === 'running' && <Button variant="secondary" onClick={() => pause.mutate()} loading={pause.isPending}>⏸ Pause</Button>}
          {bot.status !== 'stopped' && <Button variant="ghost" onClick={() => stop.mutate()} loading={stop.isPending}>⏹ Stop</Button>}
        </div>
      </div>

      {/* Tab container */}
      <div className="rounded-xl border border-gray-700/60 bg-gray-800/50 overflow-hidden">

        {/* Tab bar */}
        <div className="flex gap-0 border-b border-gray-700/50 px-4">
          {TABS.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={['px-4 py-3 text-sm font-medium border-b-2 -mb-px transition-colors',
                tab === t.id ? 'border-brand-500 text-brand-400' : 'border-transparent text-gray-500 hover:text-gray-300'].join(' ')}
            >{t.label}</button>
          ))}
        </div>

        <div className="p-5">

          {/* ── OVERVIEW ── */}
          {tab === 'overview' && (
            <div className="space-y-5">
              <div className="grid grid-cols-3 gap-4">

                {/* Operational mode card */}
                <div className={`rounded-xl border ${mv.border} ${mv.bg} px-5 py-4 flex items-center gap-4`}>
                  <span className={`text-3xl ${mv.text}`}>{mv.icon}</span>
                  <div>
                    <p className="text-xs text-gray-500 uppercase tracking-wide mb-0.5">Operational mode</p>
                    <p className={`text-sm font-semibold ${mv.text}`}>{mv.label}</p>
                  </div>
                </div>

                <Section title="Created">
                  <p className="text-sm text-gray-200">{format(new Date(bot.created_at), 'MMM d, yyyy HH:mm')}</p>
                  <p className="text-xs text-gray-600 mt-0.5">{formatDistanceToNow(new Date(bot.created_at), { addSuffix: true })}</p>
                </Section>

                <Section title={bot.status === 'flagged' || bot.status === 'banned' ? 'Blocked since' : 'Last active'}>
                  <p className="text-sm text-gray-200">{format(new Date(bot.last_active), 'MMM d, yyyy HH:mm')}</p>
                  <p className="text-xs text-gray-600 mt-0.5">{formatDistanceToNow(new Date(bot.last_active), { addSuffix: true })}</p>
                  {(bot.status === 'flagged' || bot.status === 'banned') && <Badge variant="danger" label={bot.status} className="mt-2" />}
                </Section>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <Section title="Bot configuration">
                  <InfoRow label="Skeleton" value={bot.skeleton} mono />
                  <InfoRow label="Communication" value={bot.communication_mode} />
                  <InfoRow label="Behaviour" value={bot.behaviour_pattern} />
                  <InfoRow label="Flag count" value={<span className={bot.flag_count > 0 ? 'text-red-400 font-semibold' : 'text-gray-600'}>{bot.flag_count}</span>} />
                </Section>
                <Section title="Quick stats">
                  <div className="grid grid-cols-2 gap-3">
                    <KpiCard value={stats?.actions_today ?? 0} label="Actions today" color="blue" />
                    <KpiCard value={`${((stats?.success_rate ?? 0) * 100).toFixed(0)}%`} label="Success rate" color="green" />
                    <KpiCard value={`${stats?.uptime_hours ?? 0}h`} label="Uptime" color="purple" />
                    <KpiCard value={stats?.flag_count ?? bot.flag_count} label="Flags" color={bot.flag_count > 0 ? 'red' : 'green'} />
                  </div>
                </Section>
              </div>

              {/* Lifecycle stage */}
              <LifecycleStage bot={bot} />
            </div>
          )}

          {/* ── TASK ── */}
          {tab === 'task' && (
            <div className="space-y-4">
              {!task ? (
                <div className="text-center py-16">
                  <p className="text-gray-500 text-sm mb-1">No task assigned to this bot</p>
                  <p className="text-gray-700 text-xs">Go to the Tasks page to create or assign a task</p>
                </div>
              ) : (
                <>
                  {/* Task name / status row */}
                  <div className="flex items-center justify-between rounded-xl border border-gray-700/50 bg-gray-900/40 px-5 py-3">
                    <div className="flex items-center gap-3">
                      <h3 className="text-base font-semibold text-gray-100">{task.name}</h3>
                      <Badge variant="info" label={task.type} />
                      <Badge variant={task.status === 'running' ? 'success' : task.status === 'failed' ? 'danger' : 'gray'} label={task.status} />
                    </div>
                    <div className="flex items-center gap-3 text-xs text-gray-500">
                      <span className="text-emerald-400 tabular-nums">{task.result_count} results</span>
                      <span>·</span>
                      <span className={task.error_count > 0 ? 'text-red-400' : 'text-gray-600'}>{task.error_count} errors</span>
                      <span>·</span>
                      <span>conc. {task.concurrency}</span>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">

                    {/* Goal */}
                    <Section title="Goal">
                      {taskPayload?.goal ? (
                        <div className="space-y-3">
                          {taskPayload.goal.description && <p className="text-sm text-gray-300">{taskPayload.goal.description}</p>}
                          {taskPayload.goal.topics.length > 0 && (
                            <div>
                              <p className="text-xs text-gray-600 mb-1.5">Topics</p>
                              <div className="flex flex-wrap gap-1.5">
                                {taskPayload.goal.topics.map(t => (
                                  <span key={t} className="text-xs bg-brand-500/15 border border-brand-500/30 text-brand-300 rounded-full px-2.5 py-0.5">{t}</span>
                                ))}
                              </div>
                            </div>
                          )}
                          <InfoRow label="Target count" value={taskPayload.goal.target_count} />
                        </div>
                      ) : <p className="text-xs text-gray-600">No goal defined</p>}
                    </Section>

                    <div className="space-y-4">
                      <Section title="Method">
                        {taskPayload?.method
                          ? <div>
                              <p className="text-sm font-medium text-gray-200">{METHOD_LABELS[taskPayload.method as keyof typeof METHOD_LABELS] ?? taskPayload.method}</p>
                              <p className="text-xs text-gray-600 mt-0.5 font-mono">{taskPayload.method}</p>
                            </div>
                          : <p className="text-xs text-gray-600">Not specified</p>}
                      </Section>

                      <Section title="Algorithm">
                        {taskAlg ? (
                          <div className="space-y-2">
                            <AlgChain alg={taskAlg} />
                            <p className="text-xs text-gray-500 mt-1">{taskAlg.description}</p>
                            <div className="flex items-center gap-2">
                              <span className={`text-[10px] font-medium rounded px-1.5 py-0.5 ${RESULT_COLOURS[taskAlg.resultType]}`}>{taskAlg.resultType}</span>
                              <span className="text-xs text-gray-500">{taskAlg.platformDisplay}</span>
                            </div>
                          </div>
                        ) : taskPayload?.algorithm_id
                          ? <p className="text-sm font-mono text-gray-400">{taskPayload.algorithm_id}</p>
                          : <p className="text-xs text-gray-600">No algorithm selected</p>}
                      </Section>
                    </div>
                  </div>

                  {/* Code preview */}
                  {taskAlg && (
                    <Section title="Algorithm blueprint">
                      <pre className="text-xs text-gray-400 font-mono leading-relaxed overflow-x-auto bg-gray-900 rounded-lg p-3 border border-gray-700/40 whitespace-pre-wrap">
                        {taskAlg.code}
                      </pre>
                    </Section>
                  )}

                  {/* Bots on this task */}
                  <Section title={`All bots on this task (${taskBots.length})`}>
                    {taskBots.length === 0
                      ? <p className="text-xs text-gray-600 py-2">No other bots on this task</p>
                      : (
                        <div className="grid grid-cols-2 gap-2">
                          {taskBots.map(b => (
                            <div key={b.id} className={`flex items-center gap-2 rounded-lg border px-3 py-2 ${b.id === bot.id ? 'border-brand-500/40 bg-brand-500/5' : 'border-gray-700/40 bg-gray-800/30'}`}>
                              <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${b.status === 'running' ? 'bg-emerald-400 animate-pulse' : 'bg-gray-600'}`} />
                              <span className="text-xs font-medium text-gray-300 truncate flex-1">{b.name}</span>
                              {b.id === bot.id && <span className="text-[10px] text-brand-400 shrink-0">you</span>}
                              <Badge variant={b.status === 'running' ? 'success' : 'gray'} label={b.status} />
                            </div>
                          ))}
                        </div>
                      )}
                  </Section>
                </>
              )}
            </div>
          )}

          {/* ── RESOURCES ── */}
          {tab === 'resources' && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">

                <Section title="Social media account (Identity)">
                  {identity ? (
                    <div>
                      <InfoRow label="Display name" value={identity.display_name} />
                      <InfoRow label="Username" value={`@${identity.username}`} mono />
                      <InfoRow label="Email" value={identity.email} mono />
                      <InfoRow label="Provider" value={identity.email_provider} />
                      <InfoRow label="Location" value={identity.location} />
                      <InfoRow label="Age" value={identity.age} />
                      <InfoRow label="Status" value={
                        <Badge variant={identity.status === 'active' ? 'success' : identity.status === 'flagged' ? 'warning' : identity.status === 'burned' ? 'danger' : 'gray'} label={identity.status} />
                      } />
                      {identity.bio && <InfoRow label="Bio" value={<span className="text-xs">{identity.bio}</span>} />}
                      {identity.interests.length > 0 && (
                        <InfoRow label="Interests" value={
                          <div className="flex flex-wrap gap-1 justify-end">{identity.interests.map(i => <Badge key={i} variant="gray" label={i} />)}</div>
                        } />
                      )}
                    </div>
                  ) : (
                    <p className="text-sm text-gray-600 py-2">No identity assigned</p>
                  )}
                </Section>

                <Section title="Proxy">
                  {proxy ? (
                    <div>
                      <InfoRow label="Host" value={`${proxy.host}:${proxy.port}`} mono />
                      <InfoRow label="Protocol" value={<Badge variant="info" label={proxy.protocol} />} />
                      <InfoRow label="Type" value={proxy.type} />
                      <InfoRow label="Country" value={proxy.country} />
                      {proxy.city && <InfoRow label="City" value={proxy.city} />}
                      <InfoRow label="Provider" value={proxy.provider} />
                      <InfoRow label="Health" value={<Badge variant={proxy.is_healthy ? 'success' : 'danger'} label={proxy.is_healthy ? 'Healthy' : 'Unhealthy'} />} />
                      <InfoRow label="Last checked" value={format(new Date(proxy.last_checked), 'MMM d, HH:mm')} />
                    </div>
                  ) : (
                    <p className="text-sm text-gray-600 py-2">No proxy assigned</p>
                  )}
                </Section>
              </div>

              <Section title="Email account">
                {email ? (
                  <div className="grid grid-cols-2 gap-x-8">
                    <InfoRow label="Address" value={email.address} mono />
                    <InfoRow label="Provider" value={email.provider} />
                    <InfoRow label="Type" value={email.type.replace(/_/g, ' ')} />
                    <InfoRow label="Block history" value={<Badge variant={email.ever_blocked ? 'danger' : 'success'} label={email.ever_blocked ? 'Blocked before' : 'Clean'} />} />
                    {email.blocked_on_platforms.length > 0 && (
                      <div className="col-span-2 pt-2 border-t border-gray-700/30 mt-1">
                        <p className="text-xs text-gray-600 mb-1.5">Blocked on:</p>
                        <div className="flex flex-wrap gap-1.5">{email.blocked_on_platforms.map(p => <Badge key={p} variant="danger" label={p} />)}</div>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-sm text-gray-600 py-2">No email linked — assign one in the Emails page by setting its "used by bot"</p>
                )}
              </Section>
            </div>
          )}

          {/* ── HISTORY ── */}
          {tab === 'history' && (
            <div className="space-y-5">
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <KpiCard value={stats?.actions_today ?? 0} label="Actions today" color="blue" />
                <KpiCard value={stats?.actions_lifetime ?? 0} label="Lifetime actions" color="purple" />
                <KpiCard value={`${((stats?.success_rate ?? 0) * 100).toFixed(1)}%`} label="Success rate" color="green" />
                <KpiCard value={stats?.flag_count ?? bot.flag_count} label="Flag events" color={bot.flag_count > 0 ? 'red' : 'green'} />
              </div>

              <Section title="Actions — last 7 days">
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={mockChart}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <XAxis dataKey="day" tick={{ fill: '#6b7280', fontSize: 12 }} />
                    <YAxis tick={{ fill: '#6b7280', fontSize: 12 }} />
                    <Tooltip contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8, color: '#f3f4f6' }} />
                    <Bar dataKey="actions" fill="#4f6ef7" radius={[4, 4, 0, 0]} name="Actions" />
                    <Bar dataKey="errors" fill="#ef4444" radius={[4, 4, 0, 0]} name="Errors" />
                  </BarChart>
                </ResponsiveContainer>
              </Section>

              <Section title="Event timeline">
                <div className="space-y-2">
                  {[
                    { time: bot.created_at, event: 'Bot created', color: 'bg-gray-500' },
                    { time: bot.last_active, event: 'Last active', color: 'bg-emerald-500' },
                    ...(bot.status === 'flagged' ? [{ time: bot.updated_at, event: 'Flagged by platform', color: 'bg-red-500' }] : []),
                    ...(bot.task_id && task ? [{ time: task.created_at, event: `Task assigned: ${task.name}`, color: 'bg-brand-500' }] : []),
                  ]
                    .sort((a, b) => new Date(b.time).getTime() - new Date(a.time).getTime())
                    .map((e, i) => (
                      <div key={i} className="flex items-start gap-3 py-1.5">
                        <div className={`h-2 w-2 rounded-full mt-1.5 shrink-0 ${e.color}`} />
                        <div className="min-w-0">
                          <p className="text-sm text-gray-300">{e.event}</p>
                          <p className="text-xs text-gray-600">{format(new Date(e.time), 'MMM d, yyyy HH:mm')} · {formatDistanceToNow(new Date(e.time), { addSuffix: true })}</p>
                        </div>
                      </div>
                    ))}
                </div>
              </Section>
            </div>
          )}

          {/* ── LOGS & FLAGS ── */}
          {tab === 'logs' && (
            <div className="space-y-5">
              {flags.length > 0 && (
                <Section title={`Flag events (${flags.length})`}>
                  <div className="space-y-2">
                    {flags.map(f => (
                      <div key={f.id} className="rounded-lg border border-red-800/40 bg-red-900/10 px-4 py-3 flex items-start justify-between">
                        <div>
                          <p className="text-sm font-medium text-red-300">{f.message}</p>
                          <p className="text-xs text-gray-500 mt-1">{f.category} · {format(new Date(f.created_at), 'MMM d, HH:mm')}</p>
                        </div>
                        <Badge variant="danger" label="flag" />
                      </div>
                    ))}
                  </div>
                </Section>
              )}
              <DataTable columns={logCols} data={logs} keyExtractor={l => l.id} emptyMessage="No logs yet" />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
