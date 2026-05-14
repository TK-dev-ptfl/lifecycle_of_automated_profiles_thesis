import { useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getTasks, createTask, updateTask, deleteTask, runTask, pauseTask, stopTask, getTaskBots, assignBots, unassignBots } from '../../api/tasks'
import { getPlatforms } from '../../api/platforms'
import { getBots, runBot } from '../../api/bots'
import { DataTable, Column } from '../../components/ui/DataTable'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Modal } from '../../components/ui/Modal'
import { Input } from '../../components/ui/Input'
import { Select } from '../../components/ui/Select'
import type { Task, TaskStatus, TaskType, Bot, Platform } from '../../types'
import { format } from 'date-fns'
import {
  ALGORITHM_CATALOGUE, METHOD_LABELS, METHOD_DESC, RESULT_COLOURS,
  type MethodType, type AlgorithmDef,
} from '../../data/algorithms'

// ─── Goal payload types ───────────────────────────────────────────────────────

interface TaskGoal {
  description: string
  topics: string[]
  target_count: number
}

interface TaskPayload {
  goal?: TaskGoal
  method?: MethodType
  algorithm_id?: string
}

function parsePayload(raw: Record<string, unknown>): TaskPayload {
  return {
    goal: raw.goal as TaskGoal | undefined,
    method: raw.method as MethodType | undefined,
    algorithm_id: raw.algorithm_id as string | undefined,
  }
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const statusBadge = (s: TaskStatus) => {
  const map: Record<TaskStatus, 'success' | 'warning' | 'danger' | 'gray' | 'info'> = {
    idle: 'gray', running: 'success', paused: 'warning', completed: 'info', failed: 'danger',
  }
  return <Badge variant={map[s]} label={s} />
}

function platformForAlgorithm(alg: AlgorithmDef, platforms: Platform[]): Platform | undefined {
  return platforms.find(p => p.name.toLowerCase() === alg.platform.toLowerCase())
}

// ─── Topic tag input ──────────────────────────────────────────────────────────

function TopicInput({ topics, onChange }: { topics: string[]; onChange: (t: string[]) => void }) {
  const [draft, setDraft] = useState('')
  function add() {
    const t = draft.trim()
    if (t && !topics.includes(t)) onChange([...topics, t])
    setDraft('')
  }
  return (
    <div>
      <div className="flex gap-2 mb-2">
        <input
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); add() } }}
          placeholder="Type topic + Enter"
          className="flex-1 rounded-lg border border-gray-600 bg-gray-800 px-3 py-1.5 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
        <Button size="sm" variant="secondary" type="button" onClick={add}>Add</Button>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {topics.map(t => (
          <span key={t} className="inline-flex items-center gap-1 rounded-full bg-brand-500/20 border border-brand-500/40 text-brand-300 text-xs px-2.5 py-0.5">
            {t}
            <button type="button" onClick={() => onChange(topics.filter(x => x !== t))} className="hover:text-red-300 ml-0.5">×</button>
          </span>
        ))}
        {topics.length === 0 && <span className="text-xs text-gray-600">No topics added</span>}
      </div>
    </div>
  )
}

// ─── Algorithm picker ─────────────────────────────────────────────────────────

function AlgorithmPicker({
  selectedId, method, onSelect,
}: {
  selectedId: string
  method: MethodType | ''
  onSelect: (alg: AlgorithmDef) => void
}) {
  const filtered = method
    ? ALGORITHM_CATALOGUE.filter(a => a.compatibleMethods.includes(method as MethodType))
    : ALGORITHM_CATALOGUE

  const groups = filtered.reduce<Record<string, AlgorithmDef[]>>((acc, a) => {
    const key = a.parent
    ;(acc[key] ??= []).push(a)
    return acc
  }, {})

  return (
    <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
      {Object.entries(groups).map(([parent, algs]) => (
        <div key={parent}>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-600 mb-1 pl-1">{parent}</p>
          <div className="space-y-1">
            {algs.map(alg => (
              <button
                key={alg.id}
                type="button"
                onClick={() => onSelect(alg)}
                className={[
                  'w-full text-left rounded-lg border px-3 py-2 transition-all',
                  selectedId === alg.id
                    ? 'border-brand-500/70 bg-brand-500/10'
                    : 'border-gray-700/50 hover:border-gray-600',
                ].join(' ')}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <span className="text-xs font-mono font-semibold text-gray-200">{alg.id}</span>
                    <span className="ml-2 text-xs text-gray-500">{alg.label}</span>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <span className={`text-[10px] font-medium rounded px-1.5 py-0.5 ${RESULT_COLOURS[alg.resultType]}`}>
                      {alg.resultType}
                    </span>
                    <span className="text-[10px] text-gray-500">{alg.platformDisplay}</span>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      ))}
      {filtered.length === 0 && (
        <p className="text-xs text-gray-600 py-4 text-center">No algorithms compatible with selected method</p>
      )}
    </div>
  )
}

// ─── Task definition modal ────────────────────────────────────────────────────

function TaskDefinitionModal({
  task, platforms, allBots, isOpen, onClose, onSaved,
}: {
  task: Task | null
  platforms: Platform[]
  allBots: Bot[]
  isOpen: boolean
  onClose: () => void
  onSaved: () => void
}) {
  const qc = useQueryClient()
  const isEdit = !!task
  const parsed = task ? parsePayload(task.payload) : {}

  const [name, setName] = useState(task?.name ?? '')
  const [type, setType] = useState<TaskType>(task?.type ?? 'scrape')
  const [concurrency, setConcurrency] = useState(task?.concurrency ?? 1)
  const [goal, setGoal] = useState<TaskGoal>(parsed.goal ?? { description: '', topics: [], target_count: 100 })
  const [method, setMethod] = useState<MethodType | ''>(parsed.method ?? '')
  const [algorithmId, setAlgorithmId] = useState(parsed.algorithm_id ?? '')
  const [platformId, setPlatformId] = useState(task?.platform_id ?? '')

  const selectedAlg = ALGORITHM_CATALOGUE.find(a => a.id === algorithmId)

  function handleAlgSelect(alg: AlgorithmDef) {
    setAlgorithmId(alg.id)
    const matched = platformForAlgorithm(alg, platforms)
    if (matched) setPlatformId(matched.id)
  }

  const invBots = () => { qc.invalidateQueries({ queryKey: ['task-bots', task?.id] }); qc.invalidateQueries({ queryKey: ['bots'] }) }
  const invAll = () => { qc.invalidateQueries({ queryKey: ['tasks'] }); invBots() }

  const { data: taskBots = [] } = useQuery({
    queryKey: ['task-bots', task?.id],
    queryFn: () => getTaskBots(task!.id),
    enabled: !!task,
  })

  const assignMut = useMutation({ mutationFn: (id: string) => assignBots(task!.id, [id]), onSuccess: invBots })
  const unassignMut = useMutation({ mutationFn: (id: string) => unassignBots(task!.id, [id]), onSuccess: invBots })

  const createMut = useMutation({ mutationFn: createTask, onSuccess: () => { invAll(); onSaved(); onClose() } })
  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<Task> }) => updateTask(id, data),
    onSuccess: () => { invAll(); onSaved() },
  })

  const runAllMut = useMutation({
    mutationFn: async () => {
      await runTask(task!.id)
      await Promise.all(taskBots.map(b => runBot(b.id)))
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bots'] }),
  })

  function handleSave() {
    const payload: Record<string, unknown> = { goal, method, algorithm_id: algorithmId }
    if (isEdit) {
      updateMut.mutate({ id: task!.id, data: { name, type, concurrency, payload } as Partial<Task> })
    } else {
      createMut.mutate({ name, type, concurrency, platform_id: platformId, payload } as Partial<Task>)
    }
  }

  const unassignedBots = allBots.filter(b => !taskBots.find(tb => tb.id === b.id))
  const selectedPlatform = platforms.find(p => p.id === platformId)
  const platformMismatch = selectedAlg && selectedAlg.platform !== 'generic' && selectedPlatform &&
    selectedPlatform.name.toLowerCase() !== selectedAlg.platform.toLowerCase()

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={isEdit ? `Edit task · ${task!.name}` : 'New task'}
      size="xl"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={handleSave} loading={createMut.isPending || updateMut.isPending} disabled={!name || !platformId}>
            {isEdit ? 'Save changes' : 'Create task'}
          </Button>
        </div>
      }
    >
      <div className="space-y-5">

        {/* Row 1: name / type / concurrency */}
        <div className="grid grid-cols-3 gap-3">
          <div className="col-span-1">
            <Input label="Task name" value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Reddit sentiment harvest" />
          </div>
          <Select
            label="Type"
            value={type}
            onChange={e => setType(e.target.value as TaskType)}
            options={['scrape', 'post', 'engage', 'monitor', 'seed', 'vote'].map(t => ({ value: t, label: t }))}
          />
          <Input label="Concurrency" type="number" value={concurrency} onChange={e => setConcurrency(+e.target.value)} />
        </div>

        <div className="grid grid-cols-2 gap-5">

          {/* Left: Goal + Method */}
          <div className="space-y-4">

            <div className="rounded-xl border border-gray-700/50 bg-gray-900/40 p-4 space-y-3">
              <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">Goal</p>
              <div>
                <label className="text-xs text-gray-400 mb-1 block">Description</label>
                <textarea
                  value={goal.description}
                  onChange={e => setGoal(g => ({ ...g, description: e.target.value }))}
                  rows={2}
                  placeholder="What should this task accomplish?"
                  className="w-full rounded-lg border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-brand-500 resize-none"
                />
              </div>
              <div>
                <label className="text-xs text-gray-400 mb-1.5 block">Topics / Keywords</label>
                <TopicInput topics={goal.topics} onChange={t => setGoal(g => ({ ...g, topics: t }))} />
              </div>
              <div>
                <label className="text-xs text-gray-400 mb-1 block">Target count</label>
                <input
                  type="number"
                  value={goal.target_count}
                  onChange={e => setGoal(g => ({ ...g, target_count: +e.target.value }))}
                  className="w-full rounded-lg border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
                />
              </div>
            </div>

            <div className="rounded-xl border border-gray-700/50 bg-gray-900/40 p-4 space-y-2">
              <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-1">Method</p>
              {(['official_api', 'unofficial_api', 'http_requests', 'headless_browser', 'classical_browser'] as MethodType[]).map(m => (
                <button key={m} type="button" onClick={() => setMethod(m)}
                  className={['w-full text-left rounded-lg border px-3 py-2 transition-all',
                    method === m ? 'border-brand-500/70 bg-brand-500/10' : 'border-gray-700/50 hover:border-gray-600'].join(' ')}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-gray-200">{METHOD_LABELS[m]}</span>
                    {method === m && <span className="text-[10px] text-brand-400">✓ selected</span>}
                  </div>
                  <p className="text-xs text-gray-500 mt-0.5">{METHOD_DESC[m]}</p>
                </button>
              ))}
            </div>
          </div>

          {/* Right: Algorithm + Platform + Bots */}
          <div className="space-y-4">

            <div className="rounded-xl border border-gray-700/50 bg-gray-900/40 p-4">
              <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-3">Algorithm</p>
              <AlgorithmPicker selectedId={algorithmId} method={method} onSelect={handleAlgSelect} />
              {selectedAlg && (
                <div className="mt-3 pt-3 border-t border-gray-700/40 space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono text-xs text-brand-300">{selectedAlg.id}</span>
                    <span className="text-gray-600 text-xs">extends</span>
                    <span className="font-mono text-xs text-gray-400">{selectedAlg.parent}</span>
                    <span className="text-gray-600 text-xs">extends</span>
                    <span className="font-mono text-xs text-gray-600">BaseAlgorithm</span>
                  </div>
                  <p className="text-xs text-gray-500">{selectedAlg.description}</p>
                </div>
              )}
            </div>

            <div className="rounded-xl border border-gray-700/50 bg-gray-900/40 p-4">
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">Social Media</p>
                {selectedAlg && <span className="text-[10px] text-gray-600">auto-set from algorithm</span>}
              </div>
              {platformMismatch && (
                <div className="mb-2 rounded-lg bg-red-900/20 border border-red-700/40 px-3 py-2 text-xs text-red-300">
                  ⚠ Algorithm expects <strong>{selectedAlg?.platformDisplay}</strong> — platform mismatch
                </div>
              )}
              <Select
                value={platformId}
                onChange={e => setPlatformId(e.target.value)}
                options={platforms.map(p => ({ value: p.id, label: p.display_name }))}
                placeholder="Select platform"
              />
            </div>

            {isEdit && (
              <div className="rounded-xl border border-gray-700/50 bg-gray-900/40 p-4">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                    Bots ({taskBots.length})
                  </p>
                  <Button size="sm" variant="success" onClick={() => runAllMut.mutate()}
                    loading={runAllMut.isPending} disabled={taskBots.length === 0}>
                    ▶ Run all
                  </Button>
                </div>
                <div className="space-y-1.5 mb-3 max-h-36 overflow-y-auto">
                  {taskBots.length === 0
                    ? <p className="text-xs text-gray-600 py-2 text-center">No bots assigned</p>
                    : taskBots.map(bot => (
                      <div key={bot.id} className="flex items-center justify-between rounded-lg bg-gray-800/60 border border-gray-700/40 px-3 py-1.5">
                        <div className="flex items-center gap-2 min-w-0">
                          <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${bot.status === 'running' ? 'bg-emerald-400 animate-pulse' : 'bg-gray-600'}`} />
                          <span className="text-xs font-medium text-gray-300 truncate">{bot.name}</span>
                          <Badge variant={bot.status === 'running' ? 'success' : 'gray'} label={bot.status} />
                        </div>
                        <button onClick={() => unassignMut.mutate(bot.id)} className="text-xs text-gray-600 hover:text-red-400 transition-colors ml-2 shrink-0">
                          remove
                        </button>
                      </div>
                    ))
                  }
                </div>
                {unassignedBots.length > 0 && (
                  <select onChange={e => { if (e.target.value) { assignMut.mutate(e.target.value); e.target.value = '' } }}
                    className="w-full rounded-lg border border-gray-600 bg-gray-800 px-3 py-1.5 text-sm text-gray-400 focus:outline-none">
                    <option value="">+ Add bot to task…</option>
                    {unassignedBots.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
                  </select>
                )}
              </div>
            )}
          </div>
        </div>

      </div>
    </Modal>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function TasksPage() {
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [editingTask, setEditingTask] = useState<Task | null>(null)

  const { data: tasks = [], isLoading } = useQuery({ queryKey: ['tasks'], queryFn: getTasks, refetchInterval: 10000 })
  const { data: platforms = [] } = useQuery({ queryKey: ['platforms'], queryFn: getPlatforms })
  const { data: allBots = [] } = useQuery({ queryKey: ['bots'], queryFn: () => getBots() })

  const inv = () => qc.invalidateQueries({ queryKey: ['tasks'] })
  const run = useMutation({ mutationFn: runTask, onSuccess: inv })
  const pause = useMutation({ mutationFn: pauseTask, onSuccess: inv })
  const stop = useMutation({ mutationFn: stopTask, onSuccess: inv })
  const del = useMutation({ mutationFn: deleteTask, onSuccess: inv })

  const getAlgLabel = useCallback((task: Task) => {
    const p = parsePayload(task.payload)
    if (!p.algorithm_id) return null
    const alg = ALGORITHM_CATALOGUE.find(a => a.id === p.algorithm_id)
    return alg ? `${alg.id} · ${alg.platformDisplay}` : p.algorithm_id
  }, [])

  const columns: Column<Task>[] = [
    {
      key: 'name', header: 'Name',
      render: t => (
        <div>
          <button onClick={() => setEditingTask(t)} className="font-medium text-gray-100 hover:text-brand-300 transition-colors text-left">
            {t.name}
          </button>
          {getAlgLabel(t) && <p className="text-[11px] text-gray-600 mt-0.5 font-mono">{getAlgLabel(t)}</p>}
        </div>
      ),
    },
    { key: 'type', header: 'Type', render: t => <Badge variant="info" label={t.type} /> },
    {
      key: 'method', header: 'Method',
      render: t => {
        const m = parsePayload(t.payload).method
        return m ? <span className="text-xs text-gray-400">{METHOD_LABELS[m]}</span> : <span className="text-xs text-gray-700">—</span>
      },
    },
    { key: 'status', header: 'Status', render: t => statusBadge(t.status) },
    { key: 'concurrency', header: 'Conc.', render: t => <span className="text-gray-400 tabular-nums">{t.concurrency}</span> },
    { key: 'results', header: 'Results', render: t => <span className="text-emerald-400 tabular-nums">{t.result_count}</span> },
    { key: 'errors', header: 'Errors', render: t => <span className={`tabular-nums ${t.error_count > 0 ? 'text-red-400' : 'text-gray-600'}`}>{t.error_count}</span> },
    { key: 'created', header: 'Created', render: t => <span className="text-gray-500 text-xs">{format(new Date(t.created_at), 'MMM d, HH:mm')}</span> },
    {
      key: 'actions', header: '',
      render: t => (
        <div className="flex gap-1.5">
          <Button size="sm" variant="ghost" onClick={() => setEditingTask(t)}>Edit</Button>
          {t.status !== 'running' && <Button size="sm" variant="success" onClick={() => run.mutate(t.id)}>▶</Button>}
          {t.status === 'running' && <Button size="sm" variant="secondary" onClick={() => pause.mutate(t.id)}>⏸</Button>}
          {t.status !== 'idle' && <Button size="sm" variant="ghost" onClick={() => stop.mutate(t.id)}>⏹</Button>}
          <Button size="sm" variant="danger" onClick={() => del.mutate(t.id)}>✕</Button>
        </div>
      ),
    },
  ]

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: 'Total', value: tasks.length, color: 'text-gray-200' },
          { label: 'Running', value: tasks.filter(t => t.status === 'running').length, color: 'text-emerald-400' },
          { label: 'Completed', value: tasks.filter(t => t.status === 'completed').length, color: 'text-blue-400' },
          { label: 'Failed', value: tasks.filter(t => t.status === 'failed').length, color: 'text-red-400' },
        ].map(s => (
          <div key={s.label} className="rounded-xl border border-gray-700/60 bg-gray-800/40 px-5 py-4">
            <p className={`text-2xl font-bold tabular-nums ${s.color}`}>{s.value}</p>
            <p className="text-xs text-gray-500 mt-0.5">{s.label}</p>
          </div>
        ))}
      </div>

      <div className="rounded-xl border border-gray-700/50 bg-gray-900/40 overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-700/40">
          <h2 className="text-sm font-semibold text-gray-100">Tasks</h2>
          <Button onClick={() => setShowCreate(true)}>+ New Task</Button>
        </div>
        <DataTable columns={columns} data={tasks} keyExtractor={t => t.id} loading={isLoading} emptyMessage="No tasks — create one to get started" />
      </div>

      <TaskDefinitionModal task={null} platforms={platforms} allBots={allBots}
        isOpen={showCreate} onClose={() => setShowCreate(false)} onSaved={inv} />

      {editingTask && (
        <TaskDefinitionModal key={editingTask.id} task={editingTask} platforms={platforms} allBots={allBots}
          isOpen onClose={() => setEditingTask(null)} onSaved={inv} />
      )}
    </div>
  )
}
