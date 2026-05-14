import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getBots, pauseBot, stopBot, deleteBot, createBot, updateBot } from '../../api/bots'
import { getIdentities } from '../../api/identities'
import { getTasks } from '../../api/tasks'
import { DataTable, Column } from '../../components/ui/DataTable'
import { Badge } from '../../components/ui/Badge'
import { StatusDot } from '../../components/ui/StatusDot'
import { Button } from '../../components/ui/Button'
import { Modal } from '../../components/ui/Modal'
import { Select } from '../../components/ui/Select'
import { Card } from '../../components/ui/Card'
import type { Bot, BotStatus, Task } from '../../types'
import { formatDistanceToNow } from 'date-fns'
import { ALGORITHM_CATALOGUE } from '../../data/algorithms'

type OpMode = 'running_task' | 'in_pipeline' | 'not_running' | 'blocked'

interface LocalIdentity {
  id: string
  display_name: string
  username: string
  password?: string
}

function deriveOpMode(bot: Bot): OpMode {
  if (bot.status === 'flagged' || bot.status === 'banned') return 'blocked'
  if (bot.state === 'in_pipeline') return 'in_pipeline'
  if (bot.state === 'in_task') return 'running_task'
  if (bot.state === 'blocked') return 'blocked'
  if (bot.status === 'running' && bot.task_id) return 'running_task'
  if (bot.status === 'running') return 'in_pipeline'
  return 'not_running'
}

const OP_STYLE: Record<OpMode, { label: string; cls: string; dot: string }> = {
  running_task: { label: '▶ Running Task',  cls: 'text-emerald-400 bg-emerald-900/30 border-emerald-700/50', dot: 'bg-emerald-400' },
  in_pipeline:  { label: '⟳ In Pipeline',   cls: 'text-blue-400 bg-blue-900/30 border-blue-700/50',         dot: 'bg-blue-400'    },
  not_running:  { label: '⏹ Idle',          cls: 'text-gray-500 bg-gray-800/40 border-gray-700/40',          dot: 'bg-gray-600'    },
  blocked:      { label: '⚠ Blocked',       cls: 'text-red-400 bg-red-900/30 border-red-700/50',             dot: 'bg-red-400'     },
}

const statusBadge = (s: BotStatus) => {
  const map: Record<BotStatus, 'success' | 'warning' | 'gray' | 'danger'> = {
    running: 'success', paused: 'warning', stopped: 'gray', flagged: 'warning', banned: 'danger',
  }
  return <Badge variant={map[s]} label={s} />
}

function ResourceDots({ bot, emailByBot }: { bot: Bot; emailByBot: Record<string, unknown> }) {
  const items = [
    { key: 'identity', label: 'I', title: 'Identity', active: !!bot.identity_id },
    { key: 'proxy',    label: 'P', title: 'Proxy',    active: !!bot.proxy_id },
    { key: 'email',    label: 'E', title: 'Email',    active: !!emailByBot[bot.id] },
  ]
  return (
    <div className="flex items-center gap-1.5">
      {items.map(({ key, label, title, active }) => (
        <span
          key={key}
          title={`${title}: ${active ? 'assigned' : 'not assigned'}`}
          className={`w-5 h-5 rounded text-[10px] font-bold flex items-center justify-center border ${
            active
              ? 'bg-emerald-900/40 border-emerald-700/60 text-emerald-400'
              : 'bg-gray-800 border-gray-700 text-gray-600'
          }`}
        >
          {label}
        </span>
      ))}
    </div>
  )
}

function TaskCell({ bot, taskMap }: { bot: Bot; taskMap: Record<string, Task> }) {
  if (!bot.task_id) return <span className="text-gray-700 text-xs">—</span>
  const task = taskMap[bot.task_id]
  if (!task) return <span className="text-gray-600 text-xs font-mono">{bot.task_id.slice(0, 8)}…</span>

  const algId = (task.payload as any)?.algorithm_id as string | undefined
  const alg = algId ? ALGORITHM_CATALOGUE.find(a => a.id === algId) : undefined

  return (
    <div className="min-w-0">
      <p className="text-sm text-gray-200 truncate">{task.name}</p>
      {alg && (
        <p className="text-xs text-gray-500 truncate font-mono">{alg.id}</p>
      )}
    </div>
  )
}

export default function FleetPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [selected, setSelected] = useState<string[]>([])
  const [showCreate, setShowCreate] = useState(false)
  const [newBot, setNewBot] = useState({ platform_id: 'a0000000-0000-0000-0000-000000000001', identity_id: '' })
  const [filters, setFilters] = useState({ status: '' })

  const { data: bots = [], isLoading } = useQuery({
    queryKey: ['bots', filters],
    queryFn: () => getBots(Object.fromEntries(Object.entries(filters).filter(([, v]) => v))),
    refetchInterval: 10000,
  })
  const { data: identities = [] } = useQuery({ queryKey: ['identities'], queryFn: () => getIdentities() })
  const { data: tasks = [] } = useQuery({ queryKey: ['tasks'], queryFn: getTasks })
  const localIdentities: LocalIdentity[] = identities.map((i) => ({
    id: i.id,
    display_name: i.display_name,
    username: i.username,
  }))

  const taskMap: Record<string, Task> = Object.fromEntries(tasks.map(t => [t.id, t]))

  // Build email-to-bot map from localStorage
  const emailAccounts: any[] = (() => {
    try { return JSON.parse(localStorage.getItem('email_accounts') || '[]') } catch { return [] }
  })()
  const emailByBot: Record<string, unknown> = Object.fromEntries(
    emailAccounts.filter((e: any) => e.used_by_bot_id).map((e: any) => [e.used_by_bot_id, e])
  )

  const pause = useMutation({ mutationFn: pauseBot, onSuccess: () => qc.invalidateQueries({ queryKey: ['bots'] }) })
  const stop  = useMutation({ mutationFn: stopBot,  onSuccess: () => qc.invalidateQueries({ queryKey: ['bots'] }) })
  const del   = useMutation({ mutationFn: deleteBot, onSuccess: () => qc.invalidateQueries({ queryKey: ['bots'] }) })
  const create = useMutation({
    mutationFn: async (payload: Partial<Bot>) => {
      const created = await createBot(payload)
      await updateBot(created.id, { state: 'in_pipeline', status: 'running' } as Partial<Bot>)
      const existing = (() => {
        try { return JSON.parse(localStorage.getItem('pipeline_progress_v2') || '{}') } catch { return {} }
      })()
      existing[created.id] = {
        pipelineId: 'rd-creation',
        currentStep: 0,
        completedSteps: [],
        manualInputs: {},
      }
      localStorage.setItem('pipeline_progress_v2', JSON.stringify(existing))
      return created
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bots'] })
      setShowCreate(false)
      setNewBot((prev) => ({ ...prev, identity_id: '' }))
    },
  })

  const columns: Column<Bot>[] = [
    {
      key: 'name', header: 'Bot',
      render: (b) => (
        <div>
          <button
            onClick={() => navigate(`/bots/${b.id}`)}
            className="font-medium text-gray-100 hover:text-brand-400 transition-colors text-left leading-tight"
          >
            {b.name}
          </button>
          <p className="text-xs text-gray-600 mt-0.5">
            Reddit
          </p>
        </div>
      ),
    },
    {
      key: 'password' as any, header: 'Password',
      render: (b) => (
        <span className="font-mono text-xs text-gray-300">{b.password || '—'}</span>
      ),
    },
    {
      key: 'op_mode' as any, header: 'Operation',
      render: (b) => {
        const mode = deriveOpMode(b)
        const s = OP_STYLE[mode]
        return (
          <span className={`inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-lg border font-medium ${s.cls}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
            {s.label}
          </span>
        )
      },
    },
    {
      key: 'task_id' as any, header: 'Task / Algorithm',
      render: (b) => <TaskCell bot={b} taskMap={taskMap} />,
    },
    {
      key: 'resources' as any, header: 'Resources',
      render: (b) => <ResourceDots bot={b} emailByBot={emailByBot} />,
    },
    {
      key: 'status', header: 'Status',
      render: (b) => (
        <div className="flex items-center gap-2">
          <StatusDot status={b.status} />
          {statusBadge(b.status)}
        </div>
      ),
    },
    {
      key: 'flags', header: 'Flags',
      render: (b) => (
        <div className="text-center">
          <span className={b.flag_count > 0 ? 'text-red-400 font-semibold' : 'text-gray-700'}>
            {b.flag_count}
          </span>
        </div>
      ),
    },
    {
      key: 'last_active', header: 'Last Active',
      render: (b) => (
        <div>
          <span className="text-gray-500 text-xs">
            {b.last_active ? formatDistanceToNow(new Date(b.last_active), { addSuffix: true }) : '—'}
          </span>
          <p className="text-xs text-gray-700 mt-0.5">
            created {formatDistanceToNow(new Date(b.created_at), { addSuffix: true })}
          </p>
        </div>
      ),
    },
    {
      key: 'actions', header: '',
      render: (b) => (
        <div className="flex items-center gap-1">
          {b.status === 'running' && (
            <Button size="sm" variant="secondary" onClick={(e) => { e.stopPropagation(); pause.mutate(b.id) }}>Pause</Button>
          )}
          {b.status !== 'stopped' && (
            <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); stop.mutate(b.id) }}>Stop</Button>
          )}
          <Button size="sm" variant="danger" onClick={(e) => { e.stopPropagation(); del.mutate(b.id) }}>✕</Button>
        </div>
      ),
    },
  ]

  const summaryStats = {
    running:  bots.filter(b => b.status === 'running').length,
    inTask:   bots.filter(b => b.status === 'running' && !!b.task_id).length,
    flagged:  bots.filter(b => b.status === 'flagged' || b.status === 'banned').length,
    idle:     bots.filter(b => b.status !== 'running' && b.status !== 'flagged' && b.status !== 'banned').length,
  }

  const createFromSelection = () => {
    const identity = localIdentities.find(i => i.id === newBot.identity_id)
    if (!identity) return
    create.mutate({
      platform_id: newBot.platform_id,
      identity_id: newBot.identity_id,
      password: identity.password,
      name: identity.username || identity.display_name || `bot_${identity.id.slice(0, 8)}`,
    })
  }

  return (
    <div className="space-y-5">
      {/* Summary strip */}
      <div className="grid grid-cols-5 gap-4">
        {[
          { label: 'Total Bots',    value: bots.length,          color: 'text-gray-200'   },
          { label: 'Running Task',  value: summaryStats.inTask,   color: 'text-emerald-400' },
          { label: 'In Pipeline',   value: summaryStats.running - summaryStats.inTask, color: 'text-blue-400' },
          { label: 'Idle',          value: summaryStats.idle,     color: 'text-gray-500'   },
          { label: 'Blocked',       value: summaryStats.flagged,  color: 'text-red-400'    },
        ].map((s) => (
          <div key={s.label} className="rounded-xl border border-gray-700/60 bg-gray-800/40 px-5 py-4">
            <p className={`text-2xl font-bold tabular-nums ${s.color}`}>{s.value}</p>
            <p className="text-xs text-gray-500 mt-0.5">{s.label}</p>
          </div>
        ))}
      </div>

      <Card noPad>
        <div className="flex items-center gap-3 px-5 py-4 border-b border-gray-700/50">
          <div className="flex gap-2 flex-1 flex-wrap">
            <select
              value={filters.status}
              onChange={(e) => setFilters(f => ({ ...f, status: e.target.value }))}
              className="rounded-lg border border-gray-600 bg-gray-800 px-3 py-1.5 text-sm text-gray-300 focus:outline-none focus:ring-2 focus:ring-brand-500"
            >
              <option value="">All Status</option>
              {(['running','paused','stopped','flagged','banned'] as BotStatus[]).map(s => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>

          {selected.length > 0 && (
            <div className="flex gap-2 items-center">
              <span className="text-xs text-gray-500">{selected.length} selected</span>
              <Button size="sm" variant="secondary" onClick={() => selected.forEach(id => pause.mutate(id))}>Pause All</Button>
              <Button size="sm" variant="danger" onClick={() => selected.forEach(id => del.mutate(id))}>Delete</Button>
            </div>
          )}

          <Button onClick={() => setShowCreate(true)}>+ New Bot</Button>
        </div>

        <DataTable
          columns={columns}
          data={bots}
          keyExtractor={(b) => b.id}
          loading={isLoading}
          selectable
          selectedIds={selected}
          onToggleSelect={(id) => setSelected(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id])}
          emptyMessage="No bots yet — create your first one"
        />
      </Card>

      <Modal
        title="Create New Bot"
        isOpen={showCreate}
        onClose={() => setShowCreate(false)}
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowCreate(false)}>Cancel</Button>
              <Button
              loading={create.isPending}
              disabled={!newBot.identity_id || !newBot.platform_id}
              onClick={createFromSelection}
            >
              Create
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <p className="text-sm text-gray-400">Platform: Reddit</p>
          <Select
            label="Identity"
            value={newBot.identity_id}
            onChange={(e) => setNewBot(n => ({ ...n, identity_id: e.target.value }))}
            options={localIdentities.map(i => ({
              value: i.id,
              label: `${i.display_name} (@${i.username})`,
            }))}
            placeholder="Select identity"
          />
        </div>
      </Modal>
    </div>
  )
}
