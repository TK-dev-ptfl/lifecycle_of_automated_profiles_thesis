import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getBots } from '../../api/bots'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'

interface RedditSandbox {
  id: string
  groupname: string
  profile: string
  password: string
  bot_ids: string[]
}

function uid() {
  return Math.random().toString(36).slice(2, 10)
}

function loadSandboxes(): RedditSandbox[] {
  try { return JSON.parse(localStorage.getItem('sandboxes_reddit') ?? '[]') } catch { return [] }
}

function saveSandboxes(items: RedditSandbox[]) {
  localStorage.setItem('sandboxes_reddit', JSON.stringify(items))
}

export default function SandboxesPage() {
  const { data: bots = [] } = useQuery({ queryKey: ['bots'], queryFn: () => getBots() })
  const [sandboxes, setSandboxes] = useState<RedditSandbox[]>(loadSandboxes)
  const [draft, setDraft] = useState({ groupname: '', profile: '', password: '' })

  function update(next: RedditSandbox[]) {
    setSandboxes(next)
    saveSandboxes(next)
  }

  function addSandbox() {
    if (!draft.groupname.trim() || !draft.profile.trim() || !draft.password.trim()) return
    update([{ id: uid(), bot_ids: [], ...draft }, ...sandboxes])
    setDraft({ groupname: '', profile: '', password: '' })
  }

  function removeSandbox(id: string) {
    update(sandboxes.filter(s => s.id !== id))
  }

  function toggleBot(sandboxId: string, botId: string) {
    update(sandboxes.map(s => {
      if (s.id !== sandboxId) return s
      const has = s.bot_ids.includes(botId)
      return { ...s, bot_ids: has ? s.bot_ids.filter(id => id !== botId) : [...s.bot_ids, botId] }
    }))
  }

  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-gray-700/50 bg-gray-800/30 p-4">
        <h2 className="text-sm font-semibold text-gray-100 mb-3">Reddit Sandboxes</h2>
        <div className="grid grid-cols-4 gap-3">
          <Input label="Groupname" value={draft.groupname} onChange={e => setDraft(v => ({ ...v, groupname: e.target.value }))} />
          <Input label="Profile" value={draft.profile} onChange={e => setDraft(v => ({ ...v, profile: e.target.value }))} />
          <Input label="Password" value={draft.password} onChange={e => setDraft(v => ({ ...v, password: e.target.value }))} />
          <div className="flex items-end">
            <Button className="w-full justify-center" onClick={addSandbox}>Add Sandbox</Button>
          </div>
        </div>
      </div>

      {sandboxes.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-700/50 p-10 text-center text-sm text-gray-500">
          No Reddit sandboxes yet.
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          {sandboxes.map(s => {
            const sandboxBots = bots.filter(b => s.bot_ids.includes(b.id))
            return (
              <div key={s.id} className="rounded-xl border border-gray-700/50 bg-gray-800/30 p-4 space-y-3">
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="text-sm font-semibold text-gray-100">{s.groupname}</h3>
                    <p className="text-xs text-gray-500">Profile: {s.profile}</p>
                    <p className="text-xs text-gray-600 mt-0.5">Password: {s.password}</p>
                  </div>
                  <button onClick={() => removeSandbox(s.id)} className="text-xs text-gray-600 hover:text-red-400">Remove</button>
                </div>

                <div className="text-xs text-gray-500">
                  {sandboxBots.length} bot{sandboxBots.length !== 1 ? 's' : ''} assigned
                </div>

                <div className="flex flex-wrap gap-2">
                  {sandboxBots.map(b => (
                    <span key={b.id} className="rounded-md border border-blue-700/50 bg-blue-900/20 px-2 py-1 text-xs text-blue-300">
                      {b.name}
                    </span>
                  ))}
                  {sandboxBots.length === 0 && (
                    <span className="text-xs text-gray-600">No bots assigned</span>
                  )}
                </div>

                <div className="pt-2 border-t border-gray-700/30">
                  <p className="text-xs text-gray-600 mb-2">Assign bots</p>
                  <div className="max-h-28 overflow-y-auto space-y-1">
                    {bots.map(b => (
                      <label key={b.id} className="flex items-center gap-2 text-xs text-gray-400">
                        <input
                          type="checkbox"
                          checked={s.bot_ids.includes(b.id)}
                          onChange={() => toggleBot(s.id, b.id)}
                        />
                        {b.name}
                      </label>
                    ))}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
