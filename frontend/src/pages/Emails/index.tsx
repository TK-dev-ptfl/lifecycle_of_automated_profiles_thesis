import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getBots } from '../../api/bots'
import { createEmail, createEmailPlatform, deleteEmail, deleteEmailPlatform, getEmails, getEmailPlatforms, updateEmail } from '../../api/emails'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Modal } from '../../components/ui/Modal'
import { Input } from '../../components/ui/Input'
import type { EmailAccount, EmailPlatform, EmailType } from '../../types'

const TYPE_LABELS: Record<EmailType, string> = {
  temporary: 'Temporary',
  own_mailserver: 'Own Mailserver',
  classic: 'Classic',
}

const KNOWN_PLATFORMS = ['Facebook', 'Twitter', 'Reddit', 'YouTube', 'Instagram', 'LinkedIn', 'TikTok']

function AddPlatformModal({
  isOpen, onClose, type, onAdd,
}: {
  isOpen: boolean
  onClose: () => void
  type: EmailType
  onAdd: (name: string, domain: string) => void
}) {
  const [name, setName] = useState('')
  const [domain, setDomain] = useState('')

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    onAdd(name.trim(), domain.trim())
    setName('')
    setDomain('')
    onClose()
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={`Add mail platform · ${TYPE_LABELS[type]}`}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="add-platform-form" disabled={!name.trim()}>Add platform</Button>
        </div>
      }
    >
      <form id="add-platform-form" onSubmit={handleSubmit} className="space-y-4">
        <Input label="Provider name" value={name} onChange={e => setName(e.target.value)} autoFocus />
        <Input label="Domain" value={domain} onChange={e => setDomain(e.target.value)} />
      </form>
    </Modal>
  )
}

function AddEmailModal({
  isOpen, onClose, provider, existingAddresses, onSubmit,
}: {
  isOpen: boolean
  onClose: () => void
  provider: EmailPlatform
  existingAddresses: string[]
  onSubmit: (address: string, password: string, blocked_on_platforms: string[]) => void
}) {
  const [address, setAddress] = useState('')
  const [password, setPassword] = useState('')
  const [blockedPlatforms, setBlockedPlatforms] = useState<string[]>([])
  const [error, setError] = useState('')

  function toggle(p: string) {
    setBlockedPlatforms(prev => prev.includes(p) ? prev.filter(x => x !== p) : [...prev, p])
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = address.trim().toLowerCase()
    if (!trimmed) { setError('Address is required'); return }
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(trimmed)) { setError('Enter a valid email address'); return }
    if (existingAddresses.includes(trimmed)) { setError('This address already exists'); return }
    onSubmit(trimmed, password, blockedPlatforms)
    setAddress('')
    setPassword('')
    setBlockedPlatforms([])
    setError('')
    onClose()
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={`Add email · ${provider.name}`}
      footer={<div className="flex justify-end gap-2"><Button variant="secondary" onClick={onClose}>Cancel</Button><Button type="submit" form="add-email-form">Add email</Button></div>}
    >
      <form id="add-email-form" onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1.5">Email address</label>
          <Input placeholder={`user@${provider.domain || 'example.com'}`} value={address} onChange={e => { setAddress(e.target.value); setError('') }} autoFocus />
          {error && <p className="mt-1 text-xs text-red-400">{error}</p>}
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1.5">Password</label>
          <Input type="password" placeholder="Enter password" value={password} onChange={e => setPassword(e.target.value)} />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-2">Previously blocked on platforms</label>
          <div className="flex flex-wrap gap-2">
            {KNOWN_PLATFORMS.map(p => (
              <button key={p} type="button" onClick={() => toggle(p)} className={['text-xs font-medium rounded-md px-2.5 py-1 border transition-colors', blockedPlatforms.includes(p) ? 'bg-red-900/50 border-red-700/60 text-red-300' : 'bg-gray-800 border-gray-700 text-gray-500 hover:border-gray-600 hover:text-gray-400'].join(' ')}>
                {p}
              </button>
            ))}
          </div>
        </div>
      </form>
    </Modal>
  )
}

function AccountRow({
  account, botName, onDelete, onToggleBlocked, onTogglePlatform,
}: {
  account: EmailAccount
  botName: string | null
  onDelete: () => void
  onToggleBlocked: () => void
  onTogglePlatform: (platform: string) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  return (
    <div className="rounded-lg border border-gray-700/50 bg-gray-800/20 overflow-hidden">
      <div className="flex items-center gap-3 px-4 py-3">
        <span className={['h-2 w-2 rounded-full shrink-0', account.ever_blocked ? 'bg-red-500' : botName ? 'bg-emerald-500' : 'bg-gray-600'].join(' ')} />
        <div className="flex-1 min-w-0">
          <span className="text-sm font-mono text-gray-200 block truncate">{account.address}</span>
          {account.password && <span className="text-xs text-gray-500 mt-0.5 font-mono">{showPassword ? account.password : '••••••••'}</span>}
        </div>
        {account.password && <button onClick={() => setShowPassword(!showPassword)} className="text-xs text-gray-600 hover:text-gray-400 transition-colors shrink-0">{showPassword ? 'Hide' : 'Show'}</button>}
        {botName ? <Badge variant="success" label={botName} /> : <span className="text-xs text-gray-600">—</span>}
        <button onClick={onToggleBlocked} className={['text-xs rounded px-2 py-0.5 border font-medium transition-colors shrink-0', account.ever_blocked ? 'bg-red-900/40 border-red-700/50 text-red-400 hover:bg-red-900/60' : 'bg-gray-800 border-gray-700 text-gray-600 hover:text-gray-400'].join(' ')}>
          {account.ever_blocked ? 'Blocked ✓' : 'Never blocked'}
        </button>
        <button onClick={() => setExpanded(v => !v)} className="text-xs text-gray-500 hover:text-gray-300 transition-colors shrink-0">
          {account.blocked_on_platforms.length > 0 ? `${account.blocked_on_platforms.length} platforms ▾` : 'Platforms ▾'}
        </button>
        <button onClick={onDelete} className="text-gray-700 hover:text-red-400 transition-colors text-sm shrink-0">✕</button>
      </div>
      {expanded && (
        <div className="px-4 pb-3 pt-1 border-t border-gray-700/30 bg-gray-800/20">
          <p className="text-[11px] text-gray-500 mb-2">Platforms where this email was blocked:</p>
          <div className="flex flex-wrap gap-2">
            {KNOWN_PLATFORMS.map(p => (
              <button key={p} type="button" onClick={() => onTogglePlatform(p)} className={['text-xs font-medium rounded-md px-2.5 py-1 border transition-colors', account.blocked_on_platforms.includes(p) ? 'bg-red-900/50 border-red-700/60 text-red-300' : 'bg-gray-800 border-gray-700 text-gray-500 hover:border-gray-600'].join(' ')}>
                {p}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default function EmailsPage() {
  const qc = useQueryClient()
  const [activeType, setActiveType] = useState<EmailType>('temporary')
  const [selectedProviderId, setSelectedProviderId] = useState<string | null>(null)
  const [addPlatformOpen, setAddPlatformOpen] = useState(false)
  const [addEmailOpen, setAddEmailOpen] = useState(false)

  const { data: bots = [] } = useQuery({ queryKey: ['bots'], queryFn: () => getBots() })
  const { data: providers = [] } = useQuery({ queryKey: ['email-platforms'], queryFn: () => getEmailPlatforms() })
  const { data: accounts = [] } = useQuery({ queryKey: ['emails'], queryFn: () => getEmails() })

  const createProviderMut = useMutation({
    mutationFn: (payload: { type: EmailType; name: string; domain: string }) => createEmailPlatform(payload),
    onSuccess: async () => { await qc.invalidateQueries({ queryKey: ['email-platforms'] }) },
  })
  const deleteProviderMut = useMutation({
    mutationFn: (id: string) => deleteEmailPlatform(id),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['email-platforms'] })
      await qc.invalidateQueries({ queryKey: ['emails'] })
    },
  })
  const createEmailMut = useMutation({
    mutationFn: (payload: Omit<EmailAccount, 'id' | 'created_at'>) => createEmail(payload),
    onSuccess: async () => { await qc.invalidateQueries({ queryKey: ['emails'] }) },
  })
  const updateEmailMut = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Partial<EmailAccount> }) => updateEmail(id, payload),
    onSuccess: async () => { await qc.invalidateQueries({ queryKey: ['emails'] }) },
  })
  const deleteEmailMut = useMutation({
    mutationFn: (id: string) => deleteEmail(id),
    onSuccess: async () => { await qc.invalidateQueries({ queryKey: ['emails'] }) },
  })

  const typeProviders = useMemo(() => providers.filter(p => p.type === activeType), [providers, activeType])
  const selectedProvider = useMemo(
    () => typeProviders.find(p => p.id === selectedProviderId) ?? typeProviders[0] ?? null,
    [typeProviders, selectedProviderId],
  )
  const typeAccounts = useMemo(() => accounts.filter(a => a.type === activeType), [accounts, activeType])
  const providerAccounts = useMemo(
    () => selectedProvider ? accounts.filter(a => a.provider_id === selectedProvider.id) : [],
    [accounts, selectedProvider],
  )

  function addProvider(name: string, domain: string) {
    createProviderMut.mutate({ type: activeType, name, domain })
  }

  function deleteProvider(id: string) {
    deleteProviderMut.mutate(id)
    if (selectedProviderId === id) setSelectedProviderId(null)
  }

  function addAccount(address: string, password: string, blocked_on_platforms: string[]) {
    if (!selectedProvider) return
    createEmailMut.mutate({
      type: activeType,
      provider_id: selectedProvider.id,
      address,
      password: password || undefined,
      used_by_bot_id: null,
      ever_blocked: blocked_on_platforms.length > 0,
      blocked_on_platforms,
    })
  }

  function toggleBlocked(account: EmailAccount) {
    updateEmailMut.mutate({ id: account.id, payload: { ever_blocked: !account.ever_blocked } })
  }

  function togglePlatform(account: EmailAccount, platform: string) {
    const has = account.blocked_on_platforms.includes(platform)
    const blocked_on_platforms = has ? account.blocked_on_platforms.filter(p => p !== platform) : [...account.blocked_on_platforms, platform]
    updateEmailMut.mutate({ id: account.id, payload: { blocked_on_platforms, ever_blocked: blocked_on_platforms.length > 0 || account.ever_blocked } })
  }

  const totalAll = accounts.length
  const blockedAll = accounts.filter(a => a.ever_blocked).length
  const inUseAll = accounts.filter(a => a.used_by_bot_id).length

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-gray-100">Email Accounts</h1>
          <p className="text-xs text-gray-500 mt-0.5">{totalAll} total · {inUseAll} in use by bots · {blockedAll} with block history</p>
        </div>
      </div>

      <div className="flex gap-1 rounded-xl bg-gray-800/50 p-1 border border-gray-700/50 w-fit">
        {(['temporary', 'own_mailserver', 'classic'] as EmailType[]).map(t => {
          const count = accounts.filter(a => a.type === t).length
          const blocked = accounts.filter(a => a.type === t && a.ever_blocked).length
          return (
            <button key={t} onClick={() => setActiveType(t)} className={['flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors', activeType === t ? 'bg-gray-700 text-gray-100 shadow-sm' : 'text-gray-500 hover:text-gray-300'].join(' ')}>
              <span>{TYPE_LABELS[t]}</span>
              <span className={['text-xs rounded-full px-1.5 py-0.5 font-semibold', blocked > 0 ? 'bg-red-900/60 text-red-300' : 'bg-gray-700 text-gray-500'].join(' ')}>{count}</span>
            </button>
          )
        })}
      </div>

      <div className="grid grid-cols-[220px_1fr] gap-5 items-start">
        <div className="space-y-2">
          <div className="flex items-center justify-between px-1 mb-2">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-600">Providers</p>
          </div>
          {typeProviders.length === 0 ? (
            <div className="rounded-xl border border-dashed border-gray-700/60 py-8 text-center">
              <p className="text-xs text-gray-600 mb-3">No providers yet</p>
              <Button size="sm" variant="secondary" onClick={() => setAddPlatformOpen(true)}>+ Add mail platform</Button>
            </div>
          ) : (
            <>
              {typeProviders.map(p => {
                const pAccounts = typeAccounts.filter(a => a.provider_id === p.id)
                const blocked = pAccounts.filter(a => a.ever_blocked).length
                const inUse = pAccounts.filter(a => a.used_by_bot_id).length
                return (
                  <div key={p.id} className="relative group">
                    <button onClick={() => setSelectedProviderId(p.id)} className={['w-full text-left rounded-xl border px-4 py-3 transition-all', selectedProvider?.id === p.id ? 'border-brand-500/70 bg-brand-500/10' : 'border-gray-700/50 bg-gray-900/40 hover:border-gray-600/70'].join(' ')}>
                      <div className="flex items-start justify-between gap-2 mb-1">
                        <span className="text-sm font-semibold text-gray-100 leading-snug">{p.name}</span>
                        {blocked > 0 && <span className="shrink-0 text-[10px] font-bold bg-red-900/60 text-red-300 rounded px-1.5 py-0.5">{blocked} blocked</span>}
                      </div>
                      {p.domain && <p className="text-[11px] text-gray-600 mb-2 font-mono">{p.domain}</p>}
                      <div className="flex items-center gap-3 text-xs text-gray-600"><span>{pAccounts.length} accounts</span>{inUse > 0 && <span className="text-emerald-500">{inUse} in use</span>}</div>
                    </button>
                    <button onClick={(e) => { e.stopPropagation(); deleteProvider(p.id) }} className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 text-gray-700 hover:text-red-400 transition-all text-xs px-1" title="Remove platform">✕</button>
                  </div>
                )
              })}
              <button onClick={() => setAddPlatformOpen(true)} className="w-full rounded-xl border border-dashed border-gray-700/50 py-2.5 text-xs text-gray-600 hover:text-gray-400 hover:border-gray-600 transition-colors">+ Add mail platform</button>
            </>
          )}
        </div>

        <div className="min-h-0">
          {!selectedProvider ? (
            <div className="rounded-xl border border-dashed border-gray-700/50 py-20 text-center">
              <p className="text-gray-600 text-sm">{typeProviders.length === 0 ? 'Add a mail platform to get started' : 'Select a provider to view its accounts'}</p>
            </div>
          ) : (
            <div className="rounded-xl border border-gray-700/50 bg-gray-900/40">
              <div className="px-5 py-4 border-b border-gray-700/40 flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-gray-100">{selectedProvider.name}</h2>
                  <p className="text-xs text-gray-500 mt-0.5">{providerAccounts.length} accounts · {providerAccounts.filter(a => a.used_by_bot_id).length} in use · {providerAccounts.filter(a => a.ever_blocked).length} with block history</p>
                </div>
                <Button size="sm" variant="secondary" onClick={() => setAddEmailOpen(true)}>+ Add email</Button>
              </div>
              <div className="p-3 space-y-2">
                {providerAccounts.length === 0 ? (
                  <div className="py-12 text-center"><p className="text-gray-600 text-sm">No accounts for {selectedProvider.name} yet</p></div>
                ) : (
                  providerAccounts.map(account => {
                    const bot = bots.find(b => b.id === account.used_by_bot_id)
                    return (
                      <AccountRow
                        key={account.id}
                        account={account}
                        botName={bot?.name ?? null}
                        onDelete={() => deleteEmailMut.mutate(account.id)}
                        onToggleBlocked={() => toggleBlocked(account)}
                        onTogglePlatform={(p) => togglePlatform(account, p)}
                      />
                    )
                  })
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      <AddPlatformModal isOpen={addPlatformOpen} onClose={() => setAddPlatformOpen(false)} type={activeType} onAdd={addProvider} />
      {selectedProvider && <AddEmailModal isOpen={addEmailOpen} onClose={() => setAddEmailOpen(false)} provider={selectedProvider} existingAddresses={accounts.map(a => a.address)} onSubmit={addAccount} />}
    </div>
  )
}
