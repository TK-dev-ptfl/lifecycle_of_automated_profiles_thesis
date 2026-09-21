import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getFleetSummary, getFleetHealth } from '../../api/platforms'
import { getAllPipelineStatus, type PipelineStatus } from '../../api/identities'
import { KpiCard } from '../../components/ui/KpiCard'
import { Card } from '../../components/ui/Card'
import { StatusDot } from '../../components/ui/StatusDot'
import { Badge } from '../../components/ui/Badge'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid } from 'recharts'
import type { BotStatus } from '../../types'
import { formatDistanceToNow } from 'date-fns'

const COLORS = ['#4f6ef7','#10b981','#f59e0b','#ef4444','#8b5cf6']

const mockLineData = Array.from({ length: 24 }, (_, i) => ({
  hour: `${i}:00`,
  actions: Math.floor(Math.random() * 80 + 10),
  success_rate: Math.random() * 0.3 + 0.7,
}))

// ─── Email pipeline debug logs ─────────────────────────────────────────────────
//
// Raw Playwright/pipeline messages (step start/verify lines, proxy
// selection, retries, the exact exception on failure) captured live by
// app.pipelines.email_pool.progress as the signup pipeline runs, so a broken
// run can be diagnosed here instead of digging through the backend's own
// terminal scrollback.

function pipelineRunLabel(run: PipelineStatus): string {
  return run.display_name ?? run.email ?? `identity ${run.identity_id.slice(0, 8)}`
}

function pipelineStatusDotClass(status: PipelineStatus['status']): string {
  switch (status) {
    case 'completed': return 'bg-emerald-500'
    case 'failed': return 'bg-red-500'
    case 'waiting_manual': return 'bg-amber-400'
    default: return 'bg-blue-400 animate-pulse'
  }
}

function EmailPipelineLogsCard() {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const logBoxRef = useRef<HTMLDivElement>(null)

  const { data: runs = [] } = useQuery({
    queryKey: ['identities-pipeline-status', 'monitoring'],
    queryFn: () => getAllPipelineStatus(),
    refetchInterval: 4000,
  })

  // Most recently updated first - a run that just failed or just logged
  // something new should surface to the top instead of hiding among older,
  // quiet ones.
  const sorted = [...runs].sort((a, b) => b.updated_at.localeCompare(a.updated_at))

  useEffect(() => {
    if (selectedId && sorted.some(r => r.identity_id === selectedId)) return
    if (sorted.length > 0) setSelectedId(sorted[0].identity_id)
  }, [sorted, selectedId])

  const selected = sorted.find(r => r.identity_id === selectedId) ?? null

  useEffect(() => {
    logBoxRef.current?.scrollTo({ top: logBoxRef.current.scrollHeight })
  }, [selected?.logs.length])

  return (
    <Card title="Email Pipeline Logs">
      {sorted.length === 0 ? (
        <p className="text-center text-gray-600 py-6 text-sm">
          No email pipeline runs yet. Generate an identity to start one.
        </p>
      ) : (
        <div className="grid grid-cols-3 gap-4">
          <div className="col-span-1 space-y-1.5 max-h-[420px] overflow-y-auto pr-1">
            {sorted.map(run => (
              <button
                key={run.identity_id}
                onClick={() => setSelectedId(run.identity_id)}
                className={`w-full text-left rounded-lg border px-3 py-2 transition-colors ${
                  selectedId === run.identity_id
                    ? 'border-blue-700/50 bg-blue-900/20'
                    : 'border-gray-700/40 bg-gray-800/20 hover:border-gray-600/50'
                }`}
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className={`shrink-0 h-2 w-2 rounded-full ${pipelineStatusDotClass(run.status)}`} />
                  <span className="text-sm text-gray-200 truncate">{pipelineRunLabel(run)}</span>
                </div>
                <p className="text-[11px] text-gray-600 truncate mt-0.5">
                  {run.provider} · {run.status === 'failed' ? (run.error ?? 'failed') : (run.step_name?.replace(/_/g, ' ') ?? run.status)}
                </p>
              </button>
            ))}
          </div>

          <div className="col-span-2">
            {selected ? (
              <div className="space-y-2">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className={`shrink-0 h-2 w-2 rounded-full ${pipelineStatusDotClass(selected.status)}`} />
                    <span className="text-sm font-medium text-gray-200 truncate">{pipelineRunLabel(selected)}</span>
                    <Badge variant={selected.status === 'failed' ? 'danger' : selected.status === 'completed' ? 'success' : 'gray'} label={selected.status} />
                  </div>
                  {selected.proxy && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded border border-purple-700/40 bg-purple-900/20 text-purple-300 whitespace-nowrap">
                      {selected.proxy.type} · {selected.proxy.host}:{selected.proxy.port} · {selected.proxy.country}
                    </span>
                  )}
                </div>

                {selected.error && (
                  <div className="rounded-lg border border-red-700/40 bg-red-900/20 px-3 py-2">
                    <p className="text-xs text-red-300 break-words">{selected.error}</p>
                  </div>
                )}

                <div
                  ref={logBoxRef}
                  className="rounded-lg border border-gray-700/50 bg-black/40 p-3 h-[340px] overflow-y-auto font-mono text-[11px] leading-relaxed"
                >
                  {selected.logs.length === 0 ? (
                    <p className="text-gray-600">No messages yet…</p>
                  ) : (
                    selected.logs.map((line, i) => (
                      <p
                        key={i}
                        className={
                          /rejected as invalid|Still rejected/.test(line)
                            ? 'text-amber-400'
                            : /verified OK|confirmed|checked|Account created|Entered mailbox/.test(line)
                              ? 'text-emerald-400'
                              : 'text-gray-400'
                        }
                      >
                        {line}
                      </p>
                    ))
                  )}
                </div>
              </div>
            ) : (
              <p className="text-center text-gray-600 py-6 text-sm">Select a run to see its messages</p>
            )}
          </div>
        </div>
      )}
    </Card>
  )
}

export default function MonitoringPage() {
  const { data: summary } = useQuery({ queryKey: ['fleet-summary'], queryFn: getFleetSummary, refetchInterval: 10000 })
  const { data: health = [] } = useQuery({ queryKey: ['fleet-health'], queryFn: getFleetHealth, refetchInterval: 10000 })

  const pieData = summary ? Object.entries(summary.by_status).map(([k, v]) => ({ name: k, value: v })) : []
  const modePieData = summary ? Object.entries(summary.by_mode).map(([k, v]) => ({ name: k, value: v })) : []

  return (
    <div className="space-y-5">
      {/* KPIs */}
      <div className="grid grid-cols-4 gap-4">
        <KpiCard value={summary?.total ?? 0} label="Total Bots" color="blue" />
        <KpiCard value={summary?.by_status?.running ?? 0} label="Running" color="green" />
        <KpiCard value={(summary?.by_status?.flagged ?? 0) + (summary?.by_status?.banned ?? 0)} label="Flagged/Banned" color="red" />
        <KpiCard value={`${((((summary?.by_status?.running ?? 0) / Math.max(summary?.total ?? 1, 1)) * 100)).toFixed(0)}%`} label="Uptime Rate" color="purple" />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-3 gap-5">
        <Card title="Status Distribution" className="col-span-1">
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie data={pieData} cx="50%" cy="50%" innerRadius={50} outerRadius={80} dataKey="value" nameKey="name">
                {pieData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8, color: '#f3f4f6' }} />
            </PieChart>
          </ResponsiveContainer>
          <div className="flex flex-wrap gap-2 justify-center mt-2">
            {pieData.map((d, i) => (
              <div key={d.name} className="flex items-center gap-1.5 text-xs">
                <div className="h-2 w-2 rounded-full" style={{ background: COLORS[i % COLORS.length] }} />
                <span className="text-gray-400">{d.name}: {d.value}</span>
              </div>
            ))}
          </div>
        </Card>

        <Card title="Actions per Hour (24h)" className="col-span-2">
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={mockLineData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="hour" tick={{ fill: '#6b7280', fontSize: 10 }} interval={3} />
              <YAxis tick={{ fill: '#6b7280', fontSize: 10 }} />
              <Tooltip contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8, color: '#f3f4f6' }} />
              <Line type="monotone" dataKey="actions" stroke="#4f6ef7" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </Card>
      </div>

      {/* Fleet health grid */}
      <Card title="Fleet Health">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
          {health.map((bot) => (
            <div
              key={bot.id}
              className={`rounded-lg border p-3 transition-colors ${
                bot.status === 'running' ? 'border-emerald-700/50 bg-emerald-900/10' :
                bot.status === 'flagged' || bot.status === 'banned' ? 'border-red-700/50 bg-red-900/10' :
                'border-gray-700/50 bg-gray-800/30'
              }`}
            >
              <div className="flex items-center gap-2 mb-2">
                <StatusDot status={bot.status as BotStatus} />
                <span className="text-sm font-medium text-gray-200 truncate">{bot.name}</span>
              </div>
              <div className="flex justify-between text-xs">
                <Badge variant={bot.mode === 'executing' ? 'success' : 'gray'} label={bot.mode} />
                {bot.flag_count > 0 && <span className="text-red-400">{bot.flag_count} flags</span>}
              </div>
              <p className="text-xs text-gray-600 mt-1.5">
                {bot.last_active ? formatDistanceToNow(new Date(bot.last_active), { addSuffix: true }) : '—'}
              </p>
            </div>
          ))}
          {health.length === 0 && (
            <p className="col-span-full text-center text-gray-600 py-6">No bots to monitor</p>
          )}
        </div>
      </Card>

      <EmailPipelineLogsCard />
    </div>
  )
}
