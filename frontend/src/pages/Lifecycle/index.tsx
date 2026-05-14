import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getBots } from '../../api/bots'
import { Card } from '../../components/ui/Card'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import type { Bot } from '../../types'

// ─── Pipeline definitions ────────────────────────────────────────────────────

type StepKind = 'auto' | 'manual'

interface PipelineStep {
  id: string
  name: string
  kind: StepKind
  description: string
  input: string
  output: string
}

interface Pipeline {
  id: string
  name: string
  platform: string
  color: string
  steps: PipelineStep[]
}

const PIPELINES: Pipeline[] = [
  {
    id: 'fb-create',
    name: 'Facebook Account Creation',
    platform: 'Facebook',
    color: '#4f6ef7',
    steps: [
      { id: 's1', name: 'Generate Identity', kind: 'auto', description: 'Synthesise a realistic persona from the identity pool', input: 'Config params', output: 'Identity profile' },
      { id: 's2', name: 'Register Email', kind: 'auto', description: 'Create a burner email via configured provider', input: 'Identity profile', output: 'Email credentials' },
      { id: 's3', name: 'Create Account', kind: 'auto', description: 'Register the Facebook account using the identity', input: 'Identity + email', output: 'Account draft' },
      { id: 's4', name: 'Phone Verification', kind: 'manual', description: 'Operator must provide a real SIM or SMS service code', input: 'Account draft', output: 'Verified phone' },
      { id: 's5', name: 'Upload Profile Photo', kind: 'auto', description: 'Generate and upload AI face photo to profile', input: 'Verified account', output: 'Profile with photo' },
      { id: 's6', name: 'Seed Friend Network', kind: 'auto', description: 'Follow initial friend list to bootstrap social graph', input: 'Profile', output: 'Initial network (50 friends)' },
      { id: 's7', name: 'Post Warming Content', kind: 'auto', description: 'Post benign content on a natural cadence for 7 days', input: 'Network', output: '7-day post history' },
      { id: 's8', name: 'Operator Review', kind: 'manual', description: 'Operator inspects account health before handing off to fleet', input: 'Active account', output: 'Approved bot' },
    ],
  },
  {
    id: 'tw-growth',
    name: 'Twitter / X Account Growth',
    platform: 'Twitter',
    color: '#1d9bf0',
    steps: [
      { id: 's1', name: 'Generate Identity', kind: 'auto', description: 'Synthesise persona and pick matching avatar', input: 'Config params', output: 'Identity' },
      { id: 's2', name: 'Create Account', kind: 'auto', description: 'Register account via official API or browser emulation', input: 'Identity', output: 'Account' },
      { id: 's3', name: 'Email Verification', kind: 'auto', description: 'Confirm registration email link automatically', input: 'Account', output: 'Verified account' },
      { id: 's4', name: 'CAPTCHA Challenge', kind: 'manual', description: 'Twitter may serve a CAPTCHA that requires human solving', input: 'Verified account', output: 'Unlocked account' },
      { id: 's5', name: 'Follow Seed Accounts', kind: 'auto', description: 'Follow a curated list of high-trust accounts', input: 'Unlocked account', output: 'Following list' },
      { id: 's6', name: 'Post Warming Tweets', kind: 'auto', description: 'Publish retweets and replies to build impressions', input: 'Following list', output: 'Tweet history' },
      { id: 's7', name: 'Engagement Phase', kind: 'auto', description: 'Like, reply and quote-tweet to grow interaction score', input: 'Tweet history', output: 'Engagement metrics' },
      { id: 's8', name: 'Health Check', kind: 'manual', description: 'Operator reviews metrics and approves for operational use', input: 'Engagement metrics', output: 'Operational bot' },
    ],
  },
  {
    id: 'reddit-karma',
    name: 'Reddit Karma Building',
    platform: 'Reddit',
    color: '#ff4500',
    steps: [
      { id: 's1', name: 'Generate Identity', kind: 'auto', description: 'Pick username style matching target subreddit culture', input: 'Config params', output: 'Identity' },
      { id: 's2', name: 'Register Account', kind: 'auto', description: 'Create Reddit account via API', input: 'Identity', output: 'Account' },
      { id: 's3', name: 'Email Confirmation', kind: 'auto', description: 'Confirm registration email automatically', input: 'Account', output: 'Confirmed account' },
      { id: 's4', name: 'Join Subreddits', kind: 'auto', description: 'Subscribe to target and camouflage subreddits', input: 'Confirmed account', output: 'Joined subs' },
      { id: 's5', name: 'Upvote Farming', kind: 'auto', description: 'Upvote trending posts to accumulate link karma', input: 'Joined subs', output: 'Link karma' },
      { id: 's6', name: 'CAPTCHA Solve', kind: 'manual', description: 'Reddit blocks posting until CAPTCHA is solved by operator', input: 'Link karma', output: 'Post access' },
      { id: 's7', name: 'Post Comments', kind: 'auto', description: 'Post natural-language comments in target subs', input: 'Post access', output: 'Comment history' },
      { id: 's8', name: 'Karma Verification', kind: 'manual', description: 'Operator verifies karma threshold before assigning tasks', input: 'Comment history', output: 'Karma-verified bot' },
    ],
  },
  {
    id: 'yt-channel',
    name: 'YouTube Channel Warm-up',
    platform: 'YouTube',
    color: '#ff0000',
    steps: [
      { id: 's1', name: 'Generate Identity', kind: 'auto', description: 'Create persona with matching Google account profile', input: 'Config params', output: 'Identity' },
      { id: 's2', name: 'Create Google Account', kind: 'auto', description: 'Register Google account and link to YouTube', input: 'Identity', output: 'Google account' },
      { id: 's3', name: 'Phone Verification', kind: 'manual', description: 'Google requires real SMS for new accounts', input: 'Google account', output: 'Verified account' },
      { id: 's4', name: 'Create Channel', kind: 'auto', description: 'Initialise YouTube channel with persona details', input: 'Verified account', output: 'Channel' },
      { id: 's5', name: 'Subscribe & Watch', kind: 'auto', description: 'Subscribe to seed channels and watch videos to build history', input: 'Channel', output: 'Watch history' },
      { id: 's6', name: 'Comment Seeding', kind: 'auto', description: 'Post positive comments on target and camouflage videos', input: 'Watch history', output: 'Comment history' },
      { id: 's7', name: 'Content Review', kind: 'manual', description: 'Operator approves channel appearance before operational phase', input: 'Comment history', output: 'Approved channel bot' },
    ],
  },
]

// ─── Progress store (localStorage) ───────────────────────────────────────────

interface BotProgress {
  pipelineId: string
  stepIndex: number
}

type ProgressStore = Record<string, BotProgress>

const STORAGE_KEY = 'lifecycle_progress'

function loadProgress(): ProgressStore {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}')
  } catch {
    return {}
  }
}

function saveProgress(store: ProgressStore) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(store))
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function StepCard({
  step,
  index,
  botsHere,
  isLast,
  onAdvance,
}: {
  step: PipelineStep
  index: number
  botsHere: Bot[]
  isLast: boolean
  onAdvance: (botId: string) => void
}) {
  const isManual = step.kind === 'manual'
  const hasBlockedBots = isManual && botsHere.length > 0

  return (
    <div className="flex items-stretch gap-0 shrink-0">
      <div
        className={[
          'relative w-52 rounded-xl border flex flex-col transition-all',
          hasBlockedBots
            ? 'border-amber-500/60 bg-amber-950/20 shadow-amber-900/30 shadow-lg'
            : isManual
            ? 'border-amber-700/30 bg-gray-900/60'
            : 'border-gray-700/50 bg-gray-900/40',
        ].join(' ')}
      >
        {/* Header */}
        <div className="px-3 pt-3 pb-2 border-b border-gray-700/40 flex items-start justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-[10px] font-bold text-gray-600 tabular-nums shrink-0">
              {String(index + 1).padStart(2, '0')}
            </span>
            <span className="text-xs font-semibold text-gray-200 leading-snug truncate">
              {step.name}
            </span>
          </div>
          <span
            className={[
              'shrink-0 text-[10px] font-bold uppercase tracking-wider rounded px-1.5 py-0.5',
              isManual
                ? 'bg-amber-900/60 text-amber-300'
                : 'bg-emerald-900/50 text-emerald-400',
            ].join(' ')}
          >
            {isManual ? 'manual' : 'auto'}
          </span>
        </div>

        {/* Description */}
        <p className="px-3 py-2 text-[11px] text-gray-500 leading-relaxed flex-1">
          {step.description}
        </p>

        {/* Input / Output */}
        <div className="mx-3 mb-2 rounded-lg bg-gray-800/60 border border-gray-700/40 divide-y divide-gray-700/40 text-[11px]">
          <div className="flex items-start gap-1.5 px-2 py-1.5">
            <span className="text-gray-600 font-medium shrink-0 pt-px">IN</span>
            <span className="text-gray-400 leading-snug">{step.input}</span>
          </div>
          <div className="flex items-start gap-1.5 px-2 py-1.5">
            <span className="text-gray-600 font-medium shrink-0 pt-px">OUT</span>
            <span className="text-gray-400 leading-snug">{step.output}</span>
          </div>
        </div>

        {/* Bots at this step */}
        {botsHere.length > 0 && (
          <div className="px-3 pb-3 space-y-1.5">
            {botsHere.map(bot => (
              <div
                key={bot.id}
                className={[
                  'flex items-center justify-between rounded-md px-2 py-1.5',
                  isManual
                    ? 'bg-amber-900/30 border border-amber-700/50'
                    : 'bg-gray-800/60 border border-gray-700/40',
                ].join(' ')}
              >
                <div className="flex items-center gap-1.5 min-w-0">
                  {isManual && (
                    <span className="text-amber-400 text-xs shrink-0">⚠</span>
                  )}
                  {!isManual && (
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 shrink-0 animate-pulse" />
                  )}
                  <span className="text-[11px] font-medium text-gray-300 truncate">
                    {bot.name}
                  </span>
                </div>
                {isManual && (
                  <button
                    onClick={() => onAdvance(bot.id)}
                    className="text-[10px] font-semibold text-amber-300 hover:text-amber-100 transition-colors shrink-0 ml-1"
                  >
                    Done →
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Connector arrow */}
      {!isLast && (
        <div className="flex items-center px-1 shrink-0">
          <svg width="24" height="16" viewBox="0 0 24 16" fill="none">
            <path d="M0 8 H18" stroke="#374151" strokeWidth="1.5" />
            <path d="M14 4 L20 8 L14 12" stroke="#374151" strokeWidth="1.5" strokeLinejoin="round" />
          </svg>
        </div>
      )}
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function LifecyclePage() {
  const { data: bots = [] } = useQuery({ queryKey: ['bots'], queryFn: () => getBots() })

  const [selectedPipelineId, setSelectedPipelineId] = useState(PIPELINES[0].id)
  const [progress, setProgress] = useState<ProgressStore>(loadProgress)

  const pipeline = PIPELINES.find(p => p.id === selectedPipelineId)!

  const assignedBots = bots.filter(b => progress[b.id]?.pipelineId === selectedPipelineId)
  const unassignedBots = bots.filter(b => !progress[b.id])

  // Derive manual-action alerts across ALL pipelines
  const manualAlerts: { bot: Bot; pipeline: Pipeline; step: PipelineStep; stepIndex: number }[] = []
  for (const bot of bots) {
    const prog = progress[bot.id]
    if (!prog) continue
    const pl = PIPELINES.find(p => p.id === prog.pipelineId)
    if (!pl) continue
    const step = pl.steps[prog.stepIndex]
    if (step?.kind === 'manual') {
      manualAlerts.push({ bot, pipeline: pl, step, stepIndex: prog.stepIndex })
    }
  }

  function updateProgress(store: ProgressStore) {
    setProgress(store)
    saveProgress(store)
  }

  function assignBot(botId: string) {
    updateProgress({ ...progress, [botId]: { pipelineId: selectedPipelineId, stepIndex: 0 } })
  }

  function removeBot(botId: string) {
    const next = { ...progress }
    delete next[botId]
    updateProgress(next)
  }

  function advanceBot(botId: string) {
    const prog = progress[botId]
    if (!prog) return
    const pl = PIPELINES.find(p => p.id === prog.pipelineId)
    if (!pl) return
    const nextIndex = prog.stepIndex + 1
    if (nextIndex >= pl.steps.length) {
      // Pipeline complete — remove from tracking
      const next = { ...progress }
      delete next[botId]
      updateProgress(next)
    } else {
      updateProgress({ ...progress, [botId]: { ...prog, stepIndex: nextIndex } })
    }
  }

  const autoCount = pipeline.steps.filter(s => s.kind === 'auto').length
  const manualCount = pipeline.steps.filter(s => s.kind === 'manual').length

  return (
    <div className="space-y-5">

      {/* ── Manual action banner ─────────────────────────────────────────── */}
      {manualAlerts.length > 0 && (
        <div className="rounded-xl border border-amber-600/40 bg-amber-950/30 px-4 py-3">
          <div className="flex items-center gap-2 mb-2.5">
            <span className="text-amber-400 text-sm">⚠</span>
            <span className="text-sm font-semibold text-amber-300">
              Manual Actions Required ({manualAlerts.length})
            </span>
          </div>
          <div className="space-y-1.5">
            {manualAlerts.map(({ bot, pipeline: pl, step, stepIndex }) => (
              <div
                key={bot.id}
                className="flex items-center justify-between rounded-lg bg-amber-900/20 border border-amber-700/30 px-3 py-2"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <span className="text-xs font-semibold text-gray-200 truncate">{bot.name}</span>
                  <span className="text-gray-600 text-xs">·</span>
                  <span className="text-xs text-amber-300 truncate">
                    Step {stepIndex + 1}: {step.name}
                  </span>
                  <span className="text-gray-600 text-xs">·</span>
                  <span className="text-xs text-gray-500">{pl.name}</span>
                </div>
                <Button size="sm" variant="secondary" onClick={() => advanceBot(bot.id)}>
                  Mark done
                </Button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Pipeline selector ────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {PIPELINES.map(pl => {
          const botsOnPipeline = bots.filter(b => progress[b.id]?.pipelineId === pl.id).length
          const blocked = bots.filter(b => {
            const prog = progress[b.id]
            if (!prog || prog.pipelineId !== pl.id) return false
            return pl.steps[prog.stepIndex]?.kind === 'manual'
          }).length
          return (
            <button
              key={pl.id}
              onClick={() => setSelectedPipelineId(pl.id)}
              className={[
                'text-left rounded-xl border px-4 py-3 transition-all',
                selectedPipelineId === pl.id
                  ? 'border-brand-500/70 bg-brand-500/10'
                  : 'border-gray-700/50 bg-gray-900/40 hover:border-gray-600',
              ].join(' ')}
            >
              <div className="flex items-start justify-between gap-2 mb-1">
                <span className="text-sm font-semibold text-gray-100 leading-snug">{pl.name}</span>
                {blocked > 0 && (
                  <span className="shrink-0 text-[10px] font-bold bg-amber-900/60 text-amber-300 rounded px-1.5 py-0.5">
                    {blocked} blocked
                  </span>
                )}
              </div>
              <div className="flex items-center gap-3 text-xs text-gray-500">
                <span>{pl.steps.length} steps</span>
                <span>·</span>
                <span>{botsOnPipeline} bot{botsOnPipeline !== 1 ? 's' : ''}</span>
              </div>
            </button>
          )
        })}
      </div>

      {/* ── Pipeline detail ──────────────────────────────────────────────── */}
      <div className="rounded-xl border border-gray-700/50 bg-gray-900/40">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-700/40">
          <div>
            <h2 className="text-base font-semibold text-gray-100">{pipeline.name}</h2>
            <p className="text-xs text-gray-500 mt-0.5">
              {autoCount} automated step{autoCount !== 1 ? 's' : ''} · {manualCount} manual step{manualCount !== 1 ? 's' : ''}
              {assignedBots.length > 0 && ` · ${assignedBots.length} bot${assignedBots.length !== 1 ? 's' : ''} in progress`}
            </p>
          </div>
          <div className="flex items-center gap-3 text-xs text-gray-500">
            <div className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-sm bg-emerald-500/70" />
              <span>Automated</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-sm bg-amber-500/70" />
              <span>Manual</span>
            </div>
          </div>
        </div>

        {/* Steps canvas (horizontal scroll) */}
        <div className="overflow-x-auto px-5 py-5">
          <div className="flex items-stretch gap-0 w-max">
            {pipeline.steps.map((step, i) => {
              const botsHere = assignedBots.filter(b => progress[b.id]?.stepIndex === i)
              return (
                <StepCard
                  key={step.id}
                  step={step}
                  index={i}
                  botsHere={botsHere}
                  isLast={i === pipeline.steps.length - 1}
                  onAdvance={advanceBot}
                />
              )
            })}
          </div>
        </div>
      </div>

      {/* ── Bot assignment panel ─────────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-5">

        {/* Bots in pipeline */}
        <Card title={`Bots in pipeline (${assignedBots.length})`}>
          {assignedBots.length === 0 ? (
            <p className="text-center text-gray-600 py-6 text-sm">
              No bots assigned — add from the pool below
            </p>
          ) : (
            <div className="space-y-2">
              {assignedBots.map(bot => {
                const prog = progress[bot.id]!
                const step = pipeline.steps[prog.stepIndex]
                const pct = Math.round((prog.stepIndex / pipeline.steps.length) * 100)
                return (
                  <div
                    key={bot.id}
                    className="rounded-lg border border-gray-700/50 bg-gray-800/30 px-3 py-2.5"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="text-sm font-medium text-gray-200 truncate">{bot.name}</span>
                        <Badge
                          variant={step?.kind === 'manual' ? 'warning' : 'success'}
                          label={step?.kind === 'manual' ? 'awaiting manual' : 'running'}
                        />
                      </div>
                      <button
                        onClick={() => removeBot(bot.id)}
                        className="text-xs text-gray-600 hover:text-red-400 transition-colors ml-2 shrink-0"
                      >
                        remove
                      </button>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-1.5 bg-gray-700/60 rounded-full overflow-hidden">
                        <div
                          className={[
                            'h-full rounded-full transition-all',
                            step?.kind === 'manual' ? 'bg-amber-500' : 'bg-brand-500',
                          ].join(' ')}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <span className="text-[11px] text-gray-500 shrink-0">
                        Step {prog.stepIndex + 1}/{pipeline.steps.length}
                      </span>
                    </div>
                    <p className="text-[11px] text-gray-500 mt-1 truncate">
                      {step?.name ?? 'Complete'}
                    </p>
                  </div>
                )
              })}
            </div>
          )}
        </Card>

        {/* Unassigned bot pool */}
        <Card title={`Available bots (${unassignedBots.length})`}>
          {bots.length === 0 ? (
            <p className="text-center text-gray-600 py-6 text-sm">
              No bots exist yet — create bots in the Fleet view
            </p>
          ) : unassignedBots.length === 0 ? (
            <p className="text-center text-gray-600 py-6 text-sm">
              All bots are assigned to a pipeline
            </p>
          ) : (
            <div className="space-y-2">
              {unassignedBots.map(bot => (
                <div
                  key={bot.id}
                  className="flex items-center justify-between rounded-lg border border-gray-700/50 bg-gray-800/20 px-3 py-2.5"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="h-1.5 w-1.5 rounded-full bg-gray-500 shrink-0" />
                    <span className="text-sm font-medium text-gray-300 truncate">{bot.name}</span>
                    <Badge variant="gray" label={bot.mode} />
                  </div>
                  <Button size="sm" variant="secondary" onClick={() => assignBot(bot.id)}>
                    Assign
                  </Button>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
