import { Fragment, useEffect, useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  compareBehaviourRuns,
  getBehaviourRun,
  getBehaviourRuns,
  getBehaviourScenarios,
  startBehaviourRun,
  type BehaviourCheck,
  type BehaviourEvaluation,
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
  const [useProxy, setUseProxy] = useState(true)
  const [evaluate, setEvaluate] = useState(true)
  const [publicChecks, setPublicChecks] = useState(false)
  const [manualMinutes, setManualMinutes] = useState(10)
  const [urlOverride, setUrlOverride] = useState('')
  const [runId, setRunId] = useState<string | null>(null)
  const logBox = useRef<HTMLDivElement>(null)

  const { data: scenarios = [] } = useQuery({
    queryKey: ['behaviour-scenarios'],
    queryFn: getBehaviourScenarios,
  })
  const selected = scenarios.find(s => s.key === scenario)
  const manual = selected?.style === 'manual'

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
        headless: headless && !manual,
        manual_minutes: manualMinutes,
        show_cursor: showCursor && !headless && !manual,
        use_proxy: useProxy,
        evaluate,
        public_checks: publicChecks && useProxy && evaluate,
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
    <>
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
        {manual ? (
          <label className="text-xs text-gray-500">
            Time limit (min) <span className="text-gray-700">— or click Finish</span>
            <input
              type="number" min={1} max={60} value={manualMinutes}
              onChange={e => setManualMinutes(Math.max(1, Math.min(60, Number(e.target.value) || 1)))}
              disabled={running}
              className="mt-1 w-full rounded-lg border border-gray-600 bg-gray-800 px-2 py-1.5 text-sm text-gray-200 disabled:opacity-50 focus:outline-none"
            />
          </label>
        ) : (
          <label className="text-xs text-gray-500">
            Posts to read
            <input
              type="number" min={1} max={50} value={want}
              onChange={e => setWant(Math.max(1, Math.min(50, Number(e.target.value) || 1)))}
              disabled={running}
              className="mt-1 w-full rounded-lg border border-gray-600 bg-gray-800 px-2 py-1.5 text-sm text-gray-200 disabled:opacity-50 focus:outline-none"
            />
          </label>
        )}
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
            type="checkbox" checked={headless && !manual}
            onChange={e => setHeadless(e.target.checked)}
            disabled={running || manual}
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
        <label className="col-span-2 lg:col-span-5 flex items-start gap-2 text-xs text-gray-500">
          <input
            type="checkbox" checked={useProxy}
            onChange={e => setUseProxy(e.target.checked)}
            disabled={running}
            className="mt-0.5"
          />
          <span>
            Use a proxy from the list. Each identity keeps to the same working proxy, and
            its language and time zone follow where that proxy exits. Read-only — nothing
            in the list is claimed or used up. Every run starts with no cookies.
          </span>
        </label>
        <label className="col-span-2 lg:col-span-5 flex items-start gap-2 text-xs text-gray-500">
          <input
            type="checkbox" checked={evaluate}
            onChange={e => setEvaluate(e.target.checked)}
            disabled={running}
            className="mt-0.5"
          />
          <span>
            Independent judges. After the session, score the mouse trace with the trained
            classifier and run rebrowser-bot-detector and CreepJS in the same browser.
          </span>
        </label>
        <label className="col-span-2 lg:col-span-5 flex items-start gap-2 text-xs text-gray-500">
          <input
            type="checkbox" checked={publicChecks && useProxy && evaluate}
            onChange={e => setPublicChecks(e.target.checked)}
            disabled={running || !useProxy || !evaluate}
            className="mt-0.5"
          />
          <span>
            Public detector pages too (sannysoft, BrowserScan, Pixelscan, BrowserLeaks). Proxy
            only — these sites record their visitors. Adds about a minute.
          </span>
        </label>
      </div>

      {start.isError && (
        <p className="px-4 py-2.5 text-xs text-red-300 border-b border-red-700/30 bg-red-900/15">
          Could not start: {(start.error as Error)?.message}
        </p>
      )}

      {run?.style === 'manual' && run.status === 'running' && (
        <p className="px-4 py-3 text-sm text-blue-200 border-b border-blue-700/30 bg-blue-900/20">
          Your turn. A browser window has opened on the backend machine — browse the feed by
          hand (read, scroll, like, comment), then click <b>Finish session</b> in the lab's
          Session check panel. Limit: {run.manual_minutes} min.
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

          {run.proxy?.exit_ip && (
            <div className="flex flex-wrap gap-x-4 gap-y-1 px-4 py-2.5 border-b border-gray-700/30 text-xs text-gray-500">
              <span className="text-gray-300">via {run.proxy.exit_ip}</span>
              <span>{run.proxy.country} · {run.proxy.timezone}</span>
              <span>{run.proxy.provider} {run.proxy.kind}</span>
              {run.proxy.isp && <span className="text-gray-600">{run.proxy.isp}</span>}
              {run.proxy.hosting && <span className="text-amber-400">flagged as a hosting address</span>}
            </div>
          )}

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

          {/* Independent judges: none of them was tuned against this run. */}
          {run.evaluation && Object.keys(run.evaluation).length > 0 && (
            <JudgesPanel evaluation={run.evaluation} artifactsDir={run.artifacts_dir} />
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
    <ComparePanel refreshKey={run?.status === 'running' ? null : run?.id ?? null} />
    </>
  )
}

const STYLE_LABEL: Record<string, string> = { manual: 'you (manual)', human: 'algorithm', robotic: 'robotic bot' }

// Runs side by side - by default the latest finished run of each scenario, so
// a manual session, the algorithm and the robotic control line up at a glance.
function ComparePanel({ refreshKey }: { refreshKey: string | null }) {
  const { data: runs = [] } = useQuery({
    queryKey: ['behaviour-runs', refreshKey],
    queryFn: () => getBehaviourRuns(40),
  })
  const finished = runs.filter(r => r.status === 'completed')
  const [picked, setPicked] = useState<string[] | null>(null)

  // Until the user picks, compare the latest finished run of each scenario.
  const defaults = Object.values(
    finished.reduce<Record<string, string>>((acc, r) => (acc[r.scenario] ??= r.id, acc), {}),
  )
  const ids = picked ?? defaults

  const { data: table } = useQuery({
    queryKey: ['behaviour-compare', ids.join(',')],
    queryFn: () => compareBehaviourRuns(ids),
    enabled: ids.length > 0,
  })

  const toggle = (id: string) =>
    setPicked(prev => {
      const cur = prev ?? defaults
      return cur.includes(id) ? cur.filter(x => x !== id) : [...cur, id].slice(-6)
    })

  if (finished.length === 0) return null
  let lastSection = ''
  return (
    <div className="mt-4 rounded-xl border border-gray-700/50 bg-gray-800/30 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-700/30">
        <p className="text-sm font-semibold text-gray-100">Compare runs</p>
        <p className="text-xs text-gray-500 mt-0.5">
          Same measurements for every run: the lab's verdicts and checks, the independent judges,
          and raw input statistics. Pick up to six.
        </p>
      </div>
      <div className="px-4 py-2.5 border-b border-gray-700/30 flex flex-wrap gap-x-4 gap-y-1.5 text-xs">
        {finished.slice(0, 15).map(r => (
          <label key={r.id} className="flex items-center gap-1.5 text-gray-400">
            <input type="checkbox" checked={ids.includes(r.id)} onChange={() => toggle(r.id)} />
            <span className="text-gray-300">{STYLE_LABEL[r.style ?? 'human'] ?? r.style}</span>
            <span className="text-gray-600">{r.identity} · {r.started_at.slice(5, 16).replace('T', ' ')}</span>
          </label>
        ))}
      </div>
      {table && table.runs.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-gray-400">
                <th className="px-4 py-2 font-medium sticky left-0 bg-gray-900/90">metric</th>
                {table.runs.map(r => (
                  <th key={r.id} className="px-3 py-2 font-medium min-w-[11rem]">
                    {STYLE_LABEL[r.style] ?? r.style}
                    <span className="block text-gray-600 font-normal">{r.identity} · {r.id.slice(0, 8)}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {table.rows.map((row, i) => {
                const header = row.section !== lastSection
                lastSection = row.section
                return (
                  <Fragment key={i}>
                    {header && (
                      <tr>
                        <td colSpan={table.runs.length + 1} className="px-4 pt-3 pb-1 text-[11px] uppercase tracking-wide text-gray-600">
                          {row.section}
                        </td>
                      </tr>
                    )}
                    <tr className="border-t border-gray-800/60 align-top">
                      <td className="px-4 py-1.5 text-gray-400 sticky left-0 bg-gray-900/90">{row.label}</td>
                      {row.values.map((v, j) => (
                        <td key={j} className={`px-3 py-1.5 ${compareTone(v)}`}>
                          {v === null || v === undefined ? '–' : String(v)}
                        </td>
                      ))}
                    </tr>
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function compareTone(v: string | number | null): string {
  if (typeof v !== 'string') return 'text-gray-300'
  if (v.startsWith('fail') || v === 'bot' || v === 'Reads as automated') return 'text-red-300'
  if (v.startsWith('warn')) return 'text-amber-300'
  if (v.startsWith('pass') || v === 'human' || v === 'Reads as human') return 'text-emerald-300'
  return 'text-gray-300'
}

function verdictTone(bad: boolean | undefined): string {
  if (bad === undefined) return 'text-gray-400'
  return bad ? 'text-red-400' : 'text-emerald-400'
}

// The independent judges' results, one row each: the trained mouse classifier,
// rebrowser-bot-detector, CreepJS, and (opt-in) public detector pages.
function JudgesPanel({ evaluation, artifactsDir }: { evaluation: BehaviourEvaluation; artifactsDir?: string | null }) {
  const m = evaluation.mouse_model
  const rb = evaluation.rebrowser
  const cj = evaluation.creepjs
  return (
    <div className="px-4 py-3 border-b border-gray-700/30 text-xs space-y-2.5">
      <p className="text-gray-300 font-medium">Independent judges</p>

      {m && (
        <div>
          <span className="text-gray-600">mouse classifier </span>
          <span className={verdictTone(m.verdict === 'bot' ? true : m.verdict === 'human' ? false : undefined)}>
            {m.verdict}
          </span>
          {m.bot_probability != null && (
            <span className="text-gray-500"> · bot probability {m.bot_probability} · {m.bot_like_strokes}/{m.strokes} strokes bot-like</span>
          )}
        </div>
      )}

      {rb && (
        <div>
          <span className="text-gray-600">rebrowser </span>
          {rb.error
            ? <span className="text-amber-400">{rb.error}</span>
            : <span className={verdictTone((rb.detected?.length ?? 0) > 0)}>
                {rb.detected?.length ? `${rb.detected.length} leak(s): ${rb.detected.join(', ')}` : 'no leaks'}
              </span>}
        </div>
      )}

      {cj && (
        <div>
          <span className="text-gray-600">creepjs </span>
          {cj.error
            ? <span className="text-amber-400">{cj.error}</span>
            : <>
                <span className="text-gray-400">
                  headless {cj.headless}% · like headless {cj.like_headless}% · stealth {cj.stealth}%
                </span>
                <span className={verdictTone((cj.lie_count ?? 0) > 0)}> · {cj.lie_count} lie(s)</span>
                {cj.worker_lied && <span className="text-red-400"> · worker disagrees with page</span>}
                {[...(cj.headless_flags ?? []), ...(cj.stealth_flags ?? [])].length > 0 && (
                  <p className="mt-0.5 text-gray-600">flags: {[...(cj.headless_flags ?? []), ...(cj.stealth_flags ?? [])].join(', ')}</p>
                )}
                {cj.lies && Object.keys(cj.lies).length > 0 && (
                  <p className="mt-0.5 text-gray-600 break-all">lies: {Object.keys(cj.lies).join(', ')}</p>
                )}
              </>}
        </div>
      )}

      {evaluation.public?.map((p, i) => (
        <div key={p.name ?? i}>
          <span className="text-gray-600">{p.name ?? 'public'} </span>
          {p.error
            ? <span className="text-amber-400">{p.error}</span>
            : p.passed != null
              ? <span className={verdictTone((p.failed?.length ?? 0) > 0)}>
                  {p.passed} passed{p.failed?.length ? `, failed: ${p.failed.join(', ')}` : ', none failed'}
                </span>
              : <span className="text-gray-500">{(p.highlights ?? []).slice(0, 3).join(' · ') || 'see screenshot'}</span>}
        </div>
      ))}

      {artifactsDir && (
        <p className="text-gray-600 break-all">Screenshots and trace on the backend host: {artifactsDir}</p>
      )}
    </div>
  )
}
