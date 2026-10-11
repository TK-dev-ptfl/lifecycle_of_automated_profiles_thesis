import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  getBehaviourRun,
  getBehaviourScenarios,
  startBehaviourRun,
  type BehaviourCheck,
  type BehaviourRun,
} from '../../api/algorithms'

// Runs a behaviour algorithm against a real page and shows three things: what it
// read, how it behaved, and - when the target grades sessions, as the feed lab
// does - what the page made of it.
//
// The run happens on the machine hosting the backend, not in this browser: it
// opens its own Chromium there. So this panel starts a run and then polls it,
// rather than doing any of the work itself.

const POLL_MS = 1000

function checkTone(state: BehaviourCheck['state']): string {
  if (state === 'fail') return 'border-red-700/40 bg-red-900/15 text-red-300'
  if (state === 'warn') return 'border-amber-700/40 bg-amber-900/15 text-amber-300'
  return 'border-gray-700/40 bg-gray-800/30 text-gray-400'
}

function scoreTone(value?: string): string {
  const n = Number(value)
  if (!Number.isFinite(n)) return 'text-gray-400'
  return n >= 75 ? 'text-emerald-400' : n >= 45 ? 'text-amber-400' : 'text-red-400'
}

export default function BehaviourRunner() {
  const [scenario, setScenario] = useState('feed-lab')
  const [identity, setIdentity] = useState('feed-reader-1')
  const [want, setWant] = useState(6)
  const [headless, setHeadless] = useState(false)
  const [showCursor, setShowCursor] = useState(true)
  const [urlOverride, setUrlOverride] = useState('')
  const [runId, setRunId] = useState<string | null>(null)
  const logBox = useRef<HTMLDivElement>(null)

  const { data: scenarios = [] } = useQuery({
    queryKey: ['behaviour-scenarios'],
    queryFn: getBehaviourScenarios,
  })
  const selected = scenarios.find(s => s.key === scenario)

  // Polls only while a run is in flight; a finished run never changes again.
  const { data: run } = useQuery<BehaviourRun>({
    queryKey: ['behaviour-run', runId],
    queryFn: () => getBehaviourRun(runId as string),
    enabled: !!runId,
    refetchInterval: q =>
      (q.state.data as BehaviourRun | undefined)?.status === 'running' ? POLL_MS : false,
  })

  const start = useMutation({
    mutationFn: () =>
      startBehaviourRun({
        scenario,
        identity,
        want,
        headless,
        show_cursor: showCursor && !headless,
        url: urlOverride.trim() || undefined,
      }),
    onSuccess: created => setRunId(created.id),
  })

  useEffect(() => {
    logBox.current?.scrollTo({ top: logBox.current.scrollHeight })
  }, [run?.logs.length])

  const running = run?.status === 'running' || start.isPending
  const badChecks = (run?.score?.checks ?? []).filter(c => c.state === 'fail' || c.state === 'warn')

  return (
    <div className="rounded-xl border border-gray-700/50 bg-gray-800/30 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-700/30 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-gray-100">Run behaviour algorithm</p>
          <p className="text-xs text-gray-500 mt-0.5">
            {selected?.description ??
              'Drives a real page with app.behaviour and reports what it read.'}
          </p>
        </div>
        <button
          onClick={() => start.mutate()}
          disabled={running}
          className="shrink-0 rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50 hover:bg-brand-500 transition-colors"
        >
          {running ? 'Running…' : 'Run'}
        </button>
      </div>

      {/* Parameters: the variables and the goal, which is the whole input. */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 px-4 py-3 border-b border-gray-700/30">
        <label className="text-xs text-gray-500">
          Scenario
          <select
            value={scenario}
            onChange={e => setScenario(e.target.value)}
            disabled={running}
            className="mt-1 w-full rounded-lg border border-gray-600 bg-gray-800 px-2 py-1.5 text-sm text-gray-200 disabled:opacity-50 focus:outline-none"
          >
            {scenarios.map(s => (
              <option key={s.key} value={s.key}>{s.name}</option>
            ))}
          </select>
        </label>
        <label className="text-xs text-gray-500">
          Identity <span className="text-gray-700">— picks the persona</span>
          <input
            value={identity}
            onChange={e => setIdentity(e.target.value)}
            disabled={running}
            className="mt-1 w-full rounded-lg border border-gray-600 bg-gray-800 px-2 py-1.5 text-sm text-gray-200 disabled:opacity-50 focus:outline-none"
          />
        </label>
        <label className="text-xs text-gray-500">
          Posts to read
          <input
            type="number" min={1} max={50} value={want}
            onChange={e => setWant(Math.max(1, Math.min(50, Number(e.target.value) || 1)))}
            disabled={running}
            className="mt-1 w-full rounded-lg border border-gray-600 bg-gray-800 px-2 py-1.5 text-sm text-gray-200 disabled:opacity-50 focus:outline-none"
          />
        </label>
        <label className="text-xs text-gray-500 lg:col-span-2">
          URL <span className="text-gray-700">— blank uses {selected?.url ?? 'the scenario default'}</span>
          <input
            value={urlOverride}
            onChange={e => setUrlOverride(e.target.value)}
            disabled={running}
            placeholder={selected?.url ?? ''}
            className="mt-1 w-full rounded-lg border border-gray-600 bg-gray-800 px-2 py-1.5 text-sm text-gray-200 disabled:opacity-50 focus:outline-none"
          />
        </label>
        <label className="col-span-2 lg:col-span-5 flex items-start gap-2 text-xs text-gray-500">
          <input
            type="checkbox" checked={headless}
            onChange={e => setHeadless(e.target.checked)}
            disabled={running}
            className="mt-0.5"
          />
          <span>
            Headless. Needs no screen; the identity's fingerprint is still applied, but
            headless rendering differs in ways the lab cannot see and real sites can.
            Leave off to watch the browser work.
          </span>
        </label>
        <label className="col-span-2 lg:col-span-5 flex items-start gap-2 text-xs text-gray-500">
          <input
            type="checkbox" checked={showCursor && !headless}
            onChange={e => setShowCursor(e.target.checked)}
            disabled={running || headless}
            className="mt-0.5"
          />
          <span>
            Show cursor. The simulated mouse never moves your real pointer, so this draws
            it: a red dot with a fading trail, and a blue ring on each click. Debug only —
            the dot is part of the page, so a real site could detect it.
          </span>
        </label>
      </div>

      {start.isError && (
        <p className="px-4 py-2.5 text-xs text-red-300 border-b border-red-700/30 bg-red-900/15">
          Could not start: {(start.error as Error)?.message}
        </p>
      )}

      {run && (
        <>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2.5 border-b border-gray-700/30 text-xs text-gray-500">
            <span className={
              run.status === 'completed' ? 'text-emerald-400'
                : run.status === 'failed' ? 'text-red-400' : 'text-blue-400'
            }>
              {run.status}
            </span>
            <span><span className="text-gray-300">{run.items.length}</span> read</span>
            <span>{run.elapsed_s}s</span>
            {Object.entries(run.profile).map(([k, v]) => (
              <span key={k} className="text-gray-600">{k} {String(v)}</span>
            ))}
          </div>

          {/* The machine the identity presented as - same key, same machine. */}
          {Object.keys(run.fingerprint ?? {}).length > 0 && (
            <div className="px-4 py-2.5 border-b border-gray-700/30 text-xs">
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-gray-500">
                <span className="text-gray-300">{run.fingerprint.browser} on {run.fingerprint.os}</span>
                {run.fingerprint.screen && <span>screen {run.fingerprint.screen}</span>}
                {run.fingerprint.viewport && <span>viewport {run.fingerprint.viewport}</span>}
                {run.fingerprint.cores != null && <span>{run.fingerprint.cores} cores</span>}
                {run.fingerprint.timezone && <span>{run.fingerprint.timezone}</span>}
                {run.fingerprint.languages && <span>{run.fingerprint.languages.join(', ')}</span>}
              </div>
              {run.fingerprint.gpu && <p className="mt-1 text-gray-600 break-all">{run.fingerprint.gpu}</p>}
              {run.fingerprint.user_agent && (
                <p className="mt-0.5 font-mono text-[11px] text-gray-600 break-all">{run.fingerprint.user_agent}</p>
              )}
            </div>
          )}

          {run.error && (
            <p className="px-4 py-2.5 text-xs text-red-300 border-b border-red-700/30 bg-red-900/15">
              {run.error}
            </p>
          )}

          {/* What the page thought of the session, when it grades them. */}
          {run.score && (
            <div className="px-4 py-3 border-b border-gray-700/30">
              <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
                <div>
                  <span className={`text-2xl font-bold ${scoreTone(run.score.overall)}`}>
                    {run.score.overall ?? '–'}
                  </span>
                  <span className="ml-2 text-xs text-gray-500">{run.score.verdict}</span>
                </div>
                {(['behaviour', 'fingerprint', 'recaptcha'] as const).map(k => (
                  <div key={k} className="text-xs">
                    <span className="text-gray-600">{k} </span>
                    <span className={scoreTone(run.score?.[k]?.value)}>
                      {run.score?.[k]?.value ?? '–'}
                    </span>
                    <span className="text-gray-700"> {run.score?.[k]?.detail}</span>
                  </div>
                ))}
              </div>

              {badChecks.length > 0 && (
                <ul className="mt-3 space-y-1.5">
                  {badChecks.map(c => (
                    <li key={`${c.group}:${c.name}`} className={`rounded-lg border px-3 py-2 text-xs ${checkTone(c.state)}`}>
                      {c.group && (
                        <span className="mr-1.5 opacity-60">{c.group === 'fp' ? 'fingerprint' : 'behaviour'} ·</span>
                      )}
                      <b>{c.name}</b> — {c.detail}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* What it actually read. The point of the algorithm. */}
          {run.items.length > 0 && (
            <div className="px-4 py-3 border-b border-gray-700/30 space-y-2 max-h-72 overflow-y-auto">
              {run.items.map((post, i) => (
                <div key={i} className="rounded-lg border border-gray-700/40 bg-gray-800/20 px-3 py-2">
                  <p className="text-xs text-gray-300">
                    {post.author} <span className="text-gray-600">{post.handle}</span>
                  </p>
                  <p className="text-xs text-gray-400 mt-0.5">{post.body}</p>
                  <p className="text-[11px] text-gray-600 mt-1">
                    {post.likes} likes · {post.comments} comments · {post.reposts} reposts
                  </p>
                </div>
              ))}
            </div>
          )}

          <div
            ref={logBox}
            className="px-4 py-3 h-52 overflow-y-auto font-mono text-[11px] leading-relaxed bg-black/30"
          >
            {run.logs.length === 0
              ? <p className="text-gray-600">Starting…</p>
              : run.logs.map((line, i) => (
                <p key={i} className={
                  /failed|could not|no /i.test(line) ? 'text-amber-400'
                    : /read item|clicked|scored/i.test(line) ? 'text-gray-300'
                      : 'text-gray-500'
                }>{line}</p>
              ))}
          </div>
        </>
      )}

      {!run && (
        <p className="px-4 py-6 text-center text-xs text-gray-600">
          Start the target first: <code className="text-gray-500">cd backend/tests/behaviour/test_env/feed-lab &amp;&amp; node server.mjs</code>
        </p>
      )}
    </div>
  )
}
