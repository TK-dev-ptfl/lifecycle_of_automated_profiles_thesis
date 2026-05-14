import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getPlatforms } from '../../api/platforms'
import { getBots } from '../../api/bots'
import { getTasks } from '../../api/tasks'
import { ALGORITHM_CATALOGUE, RESULT_COLOURS } from '../../data/algorithms'
import { formatDistanceToNow } from 'date-fns'
import type { Bot, Task } from '../../types'

// ─── Pipeline catalogue (mirrors Pipelines page) ──────────────────────────────

const PLATFORM_PIPELINES: Record<string, { id: string; title: string; type: 'creation' | 'trust'; steps: number }[]> = {
  facebook: [
    { id: 'fb-creation', title: 'Account Creation', type: 'creation', steps: 8 },
    { id: 'fb-trust',    title: 'Trust Building',   type: 'trust',    steps: 6 },
  ],
  twitter: [
    { id: 'tw-creation', title: 'Account Creation', type: 'creation', steps: 6 },
    { id: 'tw-trust',    title: 'Trust Building',   type: 'trust',    steps: 5 },
  ],
  reddit: [
    { id: 'rd-creation', title: 'Account Creation', type: 'creation', steps: 5 },
    { id: 'rd-trust',    title: 'Trust Building',   type: 'trust',    steps: 5 },
  ],
  youtube: [
    { id: 'yt-creation', title: 'Account Creation', type: 'creation', steps: 5 },
    { id: 'yt-trust',    title: 'Trust Building',   type: 'trust',    steps: 5 },
  ],
}

const PLATFORM_ICONS: Record<string, string> = {
  reddit: '🤖', facebook: '👥', twitter: '🐦', youtube: '▶', instagram: '📸',
}

const PLATFORM_COLOURS: Record<string, { border: string; accent: string }> = {
  twitter:  { border: 'border-sky-700/40',    accent: 'text-sky-400'    },
  reddit:   { border: 'border-orange-700/40', accent: 'text-orange-400' },
  facebook: { border: 'border-blue-700/40',   accent: 'text-blue-400'   },
  youtube:  { border: 'border-red-700/40',    accent: 'text-red-400'    },
}

type OpMode = 'running_task' | 'in_pipeline' | 'not_running' | 'blocked'

function deriveOpMode(bot: Bot): OpMode {
  if (bot.status === 'flagged' || bot.status === 'banned') return 'blocked'
  if (bot.status === 'running' && bot.task_id) return 'running_task'
  if (bot.status === 'running') return 'in_pipeline'
  return 'not_running'
}

const OP_DOT: Record<OpMode, string> = {
  running_task: 'bg-emerald-400',
  in_pipeline:  'bg-blue-400',
  not_running:  'bg-gray-600',
  blocked:      'bg-red-400',
}

const OP_LABEL: Record<OpMode, string> = {
  running_task: 'Running Task',
  in_pipeline:  'In Pipeline',
  not_running:  'Idle',
  blocked:      'Blocked',
}

// Read pipeline progress from localStorage (same key as Pipelines page)
function loadPipelineProgress(): Record<string, { pipelineId: string; currentStep: number; completedSteps: number[] }> {
  try { return JSON.parse(localStorage.getItem('pipeline_progress_v2') ?? '{}') } catch { return {} }
}

// ─── Per-platform card ────────────────────────────────────────────────────────

function PlatformCard({
  platform, bots, tasks, navigate,
}: {
  platform: { id: string; name: string; display_name: string; is_enabled: boolean }
  bots: Bot[]
  tasks: Task[]
  navigate: (path: string) => void
}) {
  const [section, setSection] = useState<'bots' | 'tasks' | 'pipelines' | 'algorithms'>('bots')
  const pipelineProgress = loadPipelineProgress()

  // Filter data that belongs to this platform
  const pBots  = bots.filter(b => b.platform_id === platform.id)
  const pTasks = tasks.filter(t => t.platform_id === platform.id)
  const algs   = ALGORITHM_CATALOGUE.filter(a => a.platform === platform.name)
  const pipes  = PLATFORM_PIPELINES[platform.name] ?? []

  // Bots in pipelines on this platform
  const botsInPipeline = pBots.filter(b => {
    const p = pipelineProgress[b.id]
    return p && pipes.some(pipe => pipe.id === p.pipelineId)
  })

  // Task goal stats
  const byType = (type: string) => pTasks.filter(t => t.type === type).reduce((s, t) => s + (t.result_count ?? 0), 0)
  const goalStats = [
    { label: 'Data records', value: byType('scrape'),  show: byType('scrape')  > 0 },
    { label: 'Posts made',   value: byType('post'),    show: byType('post')    > 0 },
    { label: 'Engagements',  value: byType('engage'),  show: byType('engage')  > 0 },
    { label: 'Votes cast',   value: byType('vote'),    show: byType('vote')    > 0 },
  ].filter(g => g.show)

  const colours = PLATFORM_COLOURS[platform.name] ?? { border: 'border-gray-700/40', accent: 'text-gray-400' }
  const TABS = ['bots', 'tasks', 'pipelines', 'algorithms'] as const

  return (
    <div className={`rounded-2xl border ${colours.border} bg-gray-800/20 overflow-hidden`}>
      {/* Header */}
      <div className="px-5 py-4 border-b border-gray-700/40 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-2xl">{PLATFORM_ICONS[platform.name] ?? '🌐'}</span>
          <div>
            <h2 className="font-semibold text-gray-100">{platform.display_name}</h2>
            <p className="text-xs text-gray-600 font-mono">{platform.name}</p>
          </div>
        </div>
        <span className={`text-xs px-2 py-0.5 rounded-full border ${platform.is_enabled ? 'text-emerald-400 border-emerald-700/50 bg-emerald-900/20' : 'text-gray-500 border-gray-700'}`}>
          {platform.is_enabled ? 'Active' : 'Disabled'}
        </span>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-4 border-b border-gray-700/40">
        {[
          { label: 'Bots',       value: pBots.length,          sub: `${pBots.filter(b => b.status === 'running').length} running`,    tab: 'bots'       },
          { label: 'Tasks',      value: pTasks.length,         sub: `${pTasks.filter(t => t.status === 'completed').length} completed`, tab: 'tasks'      },
          { label: 'Pipelines',  value: pipes.length,          sub: `${botsInPipeline.length} bots active`,                            tab: 'pipelines'  },
          { label: 'Algorithms', value: algs.length,           sub: `for ${platform.display_name}`,                                    tab: 'algorithms' },
        ].map(k => (
          <button
            key={k.tab}
            onClick={() => setSection(k.tab as typeof section)}
            className={`px-3 py-3 text-center border-r last:border-r-0 border-gray-700/40 transition-colors hover:bg-gray-700/20 ${section === k.tab ? 'bg-gray-700/30' : ''}`}
          >
            <p className={`text-xl font-bold tabular-nums ${section === k.tab ? colours.accent : 'text-gray-200'}`}>{k.value}</p>
            <p className="text-xs text-gray-500">{k.label}</p>
            <p className="text-[10px] text-gray-700 mt-0.5">{k.sub}</p>
          </button>
        ))}
      </div>

      {/* Goal stats bar */}
      {goalStats.length > 0 && (
        <div className="px-5 py-2.5 border-b border-gray-700/40 flex items-center gap-4 flex-wrap">
          <span className="text-xs text-gray-600">Goals:</span>
          {goalStats.map(g => (
            <span key={g.label} className="text-xs">
              <span className="text-gray-500">{g.label} </span>
              <span className={`font-semibold tabular-nums ${colours.accent}`}>{g.value.toLocaleString()}</span>
            </span>
          ))}
        </div>
      )}

      {/* Section content */}
      <div className="p-4 min-h-40">

        {/* BOTS */}
        {section === 'bots' && (
          <div>
            {pBots.length === 0 ? (
              <div className="text-center py-8">
                <p className="text-gray-600 text-sm">No bots on this platform</p>
                <button onClick={() => navigate('/fleet')} className="text-xs text-brand-400 hover:text-brand-300 mt-1">Go to Fleet →</button>
              </div>
            ) : (
              <div className="space-y-1.5">
                {pBots.map(b => {
                  const mode = deriveOpMode(b)
                  const pp = pipelineProgress[b.id]
                  const botPipe = pp ? pipes.find(p => p.id === pp.pipelineId) : null
                  return (
                    <button
                      key={b.id}
                      onClick={() => navigate(`/bots/${b.id}`)}
                      className="w-full flex items-center gap-3 rounded-lg border border-gray-700/30 bg-gray-800/40 px-3 py-2 hover:border-gray-600/60 hover:bg-gray-700/30 transition-colors text-left"
                    >
                      <span className={`w-2 h-2 rounded-full shrink-0 ${OP_DOT[mode]}`} />
                      <span className="text-sm text-gray-200 flex-1 truncate">{b.name}</span>
                      <span className="text-xs text-gray-500 shrink-0">{OP_LABEL[mode]}</span>
                      {botPipe && (
                        <span className="text-[10px] text-purple-400 border border-purple-700/40 rounded px-1.5 py-0.5 shrink-0">
                          {botPipe.title}
                        </span>
                      )}
                      {b.flag_count > 0 && (
                        <span className="text-xs text-red-400 shrink-0">⚑ {b.flag_count}</span>
                      )}
                    </button>
                  )
                })}
                <button onClick={() => navigate('/fleet')} className="text-xs text-gray-600 hover:text-gray-400 transition-colors mt-1">
                  View all in Fleet →
                </button>
              </div>
            )}
          </div>
        )}

        {/* TASKS */}
        {section === 'tasks' && (
          <div>
            {pTasks.length === 0 ? (
              <div className="text-center py-8">
                <p className="text-gray-600 text-sm">No tasks for this platform</p>
                <button onClick={() => navigate('/tasks')} className="text-xs text-brand-400 hover:text-brand-300 mt-1">Go to Tasks →</button>
              </div>
            ) : (
              <div className="space-y-1.5">
                {pTasks.slice(0, 8).map(t => {
                  const statusColour: Record<string, string> = {
                    running: 'text-emerald-400', completed: 'text-blue-400', failed: 'text-red-400', idle: 'text-gray-500', paused: 'text-amber-400',
                  }
                  const algId = (t.payload as any)?.algorithm_id as string | undefined
                  return (
                    <div key={t.id} className="flex items-center gap-3 rounded-lg border border-gray-700/30 bg-gray-800/40 px-3 py-2">
                      <span className={`text-xs font-medium shrink-0 ${statusColour[t.status] ?? 'text-gray-500'}`}>{t.status}</span>
                      <span className="text-sm text-gray-200 flex-1 truncate">{t.name}</span>
                      {algId && <span className="text-[10px] text-gray-600 font-mono shrink-0 truncate max-w-28">{algId}</span>}
                      <span className="text-xs text-gray-600 shrink-0">{t.result_count} results</span>
                    </div>
                  )
                })}
                {pTasks.length > 8 && <p className="text-xs text-gray-700 mt-1">+{pTasks.length - 8} more</p>}
                <button onClick={() => navigate('/tasks')} className="text-xs text-gray-600 hover:text-gray-400 transition-colors mt-1">
                  View all in Tasks →
                </button>
              </div>
            )}
          </div>
        )}

        {/* PIPELINES */}
        {section === 'pipelines' && (
          <div className="space-y-2">
            {pipes.length === 0 ? (
              <p className="text-gray-600 text-sm text-center py-8">No pipelines defined for this platform</p>
            ) : (
              pipes.map(pipe => {
                const botsHere = pBots.filter(b => {
                  const pp = pipelineProgress[b.id]
                  return pp?.pipelineId === pipe.id
                })
                return (
                  <div key={pipe.id} className="rounded-lg border border-gray-700/30 bg-gray-800/40 px-4 py-3">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${pipe.type === 'creation' ? 'bg-blue-900/40 text-blue-400' : 'bg-purple-900/40 text-purple-400'}`}>
                          {pipe.type}
                        </span>
                        <span className="text-sm font-medium text-gray-200">{pipe.title}</span>
                      </div>
                      <span className="text-xs text-gray-600">{pipe.steps} steps</span>
                    </div>
                    {botsHere.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mt-1.5">
                        {botsHere.map(b => {
                          const pp = pipelineProgress[b.id]!
                          const pct = Math.round(((pp.completedSteps.length) / pipe.steps) * 100)
                          return (
                            <span key={b.id} className="text-[10px] bg-gray-700/50 border border-gray-600/40 rounded px-1.5 py-0.5 text-gray-300">
                              {b.name} — {pct}%
                            </span>
                          )
                        })}
                      </div>
                    )}
                    {botsHere.length === 0 && (
                      <p className="text-xs text-gray-700">No bots active</p>
                    )}
                  </div>
                )
              })
            )}
            <button onClick={() => navigate('/pipelines')} className="text-xs text-gray-600 hover:text-gray-400 transition-colors">
              Manage pipelines →
            </button>
          </div>
        )}

        {/* ALGORITHMS */}
        {section === 'algorithms' && (
          <div>
            {algs.length === 0 ? (
              <p className="text-gray-600 text-sm text-center py-8">No algorithms for this platform</p>
            ) : (
              <div className="space-y-1.5">
                {algs.map(a => (
                  <div key={a.id} className="flex items-center gap-3 rounded-lg border border-gray-700/30 bg-gray-800/40 px-3 py-2">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded font-semibold ${RESULT_COLOURS[a.resultType]}`}>
                      {a.resultType}
                    </span>
                    <span className="text-sm text-gray-200 flex-1 font-mono">{a.id}</span>
                    <span className="text-xs text-gray-500 truncate max-w-32">{a.label}</span>
                  </div>
                ))}
                <button onClick={() => navigate('/algorithm')} className="text-xs text-gray-600 hover:text-gray-400 transition-colors">
                  Browse algorithm catalogue →
                </button>
              </div>
            )}
          </div>
        )}

      </div>
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function PlatformsPage() {
  const navigate = useNavigate()

  const { data: platforms = [], isLoading } = useQuery({ queryKey: ['platforms'], queryFn: getPlatforms })
  const { data: bots = [] }  = useQuery({ queryKey: ['bots'],  queryFn: () => getBots() })
  const { data: tasks = [] } = useQuery({ queryKey: ['tasks'], queryFn: getTasks })

  if (isLoading) return <div className="flex items-center justify-center h-64 text-gray-500">Loading…</div>

  const totalResults = tasks.reduce((s, t) => s + (t.result_count ?? 0), 0)
  const runningBots  = bots.filter(b => b.status === 'running').length

  return (
    <div className="space-y-5">
      {/* Global strip */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: 'Platforms',     value: platforms.filter(p => p.is_enabled).length, sub: `${platforms.length} total`,       colour: 'text-gray-200'    },
          { label: 'Active bots',   value: runningBots,                                 sub: `${bots.length} total`,             colour: 'text-emerald-400' },
          { label: 'Tasks total',   value: tasks.length,                                sub: `${tasks.filter(t => t.status === 'completed').length} completed`, colour: 'text-blue-400' },
          { label: 'Results collected', value: totalResults.toLocaleString(),           sub: 'across all platforms',             colour: 'text-purple-400'  },
        ].map(s => (
          <div key={s.label} className="rounded-xl border border-gray-700/60 bg-gray-800/40 px-5 py-4">
            <p className={`text-2xl font-bold tabular-nums ${s.colour}`}>{s.value}</p>
            <p className="text-xs text-gray-500 mt-0.5">{s.label}</p>
            <p className="text-xs text-gray-700 mt-0.5">{s.sub}</p>
          </div>
        ))}
      </div>

      {platforms.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-700 py-16 text-center text-gray-600 text-sm">
          No platforms configured yet
        </div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
          {platforms.map(p => (
            <PlatformCard key={p.id} platform={p} bots={bots} tasks={tasks} navigate={navigate} />
          ))}
        </div>
      )}
    </div>
  )
}
