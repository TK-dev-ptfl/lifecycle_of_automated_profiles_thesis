import { useState } from 'react'
import { Card } from '../../components/ui/Card'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'
import { Badge } from '../../components/ui/Badge'

interface SimReport {
  tick: number
  agents: number
  total_actions: number
  flags_raised: number
  events: string[]
}

export default function SimulationPage() {
  const [numAgents, setNumAgents] = useState(10)
  const [seed, setSeed] = useState('')
  const [running, setRunning] = useState(false)
  const [report, setReport] = useState<SimReport | null>(null)
  const [feed, setFeed] = useState<{id: string; agent: string; content: string}[]>([])
  const [eventType, setEventType] = useState('trending_topic')
  const [eventPayload, setEventPayload] = useState('{"topic": "AI news"}')

  const startSim = () => {
    setRunning(true)
    setReport({ tick: 0, agents: numAgents, total_actions: 0, flags_raised: 0, events: [] })
  }

  const tick = () => {
    if (!report) return
    const newActions = Math.floor(Math.random() * numAgents * 3)
    const newFlags = Math.random() > 0.8 ? 1 : 0
    setReport(r => r ? {
      ...r,
      tick: r.tick + 1,
      total_actions: r.total_actions + newActions,
      flags_raised: r.flags_raised + newFlags,
      events: [...r.events, `Tick ${r.tick + 1}: ${newActions} actions performed`].slice(-10),
    } : r)
    setFeed(f => [
      ...f,
      { id: Math.random().toString(36).slice(2), agent: `agent_${Math.floor(Math.random() * numAgents)}`, content: `Simulated post at tick ${report.tick + 1}` },
    ].slice(-20))
  }

  const reset = () => {
    setRunning(false)
    setReport(null)
    setFeed([])
  }

  const injectEvent = () => {
    if (!report) return
    try {
      const payload = JSON.parse(eventPayload)
      setReport(r => r ? {
        ...r,
        events: [...r.events, `Event injected: ${eventType} — ${JSON.stringify(payload)}`].slice(-10),
      } : r)
    } catch {
      alert('Invalid JSON payload')
    }
  }

  return (
    <div className="space-y-5">
      {/* Controls */}
      <Card title="Environment Controls">
        <div className="flex items-end gap-4 flex-wrap">
          <Input label="Agents" type="number" value={numAgents} onChange={(e) => setNumAgents(+e.target.value)} className="w-28" />
          <Input label="Seed (optional)" value={seed} onChange={(e) => setSeed(e.target.value)} placeholder="42" className="w-32" />
          <div className="flex gap-2">
            <Button variant="success" onClick={startSim} disabled={running}>▶ Start</Button>
            <Button variant="secondary" onClick={tick} disabled={!running}>⏭ Tick</Button>
            <Button variant="danger" onClick={reset}>↺ Reset</Button>
          </div>
        </div>
      </Card>

      {/* Status bar */}
      {report && (
        <div className="grid grid-cols-4 gap-4">
          {[
            { label: 'Tick', value: report.tick },
            { label: 'Agents', value: report.agents },
            { label: 'Total Actions', value: report.total_actions },
            { label: 'Flags Raised', value: report.flags_raised },
          ].map(s => (
            <div key={s.label} className="rounded-xl border border-gray-700/60 bg-gray-800/40 px-5 py-4">
              <p className="text-2xl font-bold tabular-nums text-gray-100">{s.value}</p>
              <p className="text-xs text-gray-500 mt-0.5">{s.label}</p>
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-2 gap-5">
        {/* Event log */}
        <Card title="Event Log">
          <div className="space-y-1 max-h-64 overflow-y-auto">
            {(report?.events ?? []).length === 0 ? (
              <p className="text-sm text-gray-600">No events yet — start the simulation</p>
            ) : (
              report!.events.map((ev, i) => (
                <p key={i} className="text-xs font-mono text-gray-400 border-b border-gray-700/30 pb-1">{ev}</p>
              ))
            )}
          </div>
        </Card>

        {/* Live feed */}
        <Card title="Live Feed">
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {feed.length === 0 ? (
              <p className="text-sm text-gray-600">Feed will populate as the simulation runs</p>
            ) : (
              feed.map((post) => (
                <div key={post.id} className="rounded-lg bg-gray-800/40 border border-gray-700/40 px-3 py-2">
                  <p className="text-xs font-medium text-brand-400">@{post.agent}</p>
                  <p className="text-xs text-gray-400 mt-0.5">{post.content}</p>
                </div>
              ))
            )}
          </div>
        </Card>
      </div>

      {/* Event injector */}
      <Card title="Event Injector">
        <div className="flex gap-4 items-end flex-wrap">
          <div>
            <label className="text-xs font-medium text-gray-400">Event Type</label>
            <select
              value={eventType}
              onChange={(e) => setEventType(e.target.value)}
              className="mt-1 block rounded-lg border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-300 focus:outline-none"
            >
              <option value="trending_topic">Trending Topic</option>
              <option value="viral_post">Viral Post</option>
              <option value="platform_crackdown">Platform Crackdown</option>
            </select>
          </div>
          <div className="flex-1">
            <label className="text-xs font-medium text-gray-400">Payload (JSON)</label>
            <input
              value={eventPayload}
              onChange={(e) => setEventPayload(e.target.value)}
              className="mt-1 w-full rounded-lg border border-gray-600 bg-gray-800 px-3 py-2 font-mono text-xs text-gray-300 focus:outline-none"
            />
          </div>
          <Button variant="secondary" onClick={injectEvent} disabled={!running}>Inject</Button>
        </div>
      </Card>
    </div>
  )
}
