import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getProxies, getProxyStats, getProxyProviders, setProxyProviderEnabled,
  createProxy, deleteProxy, testProxy, cleanupUnhealthyProxies, fetchProxiesFromFreeList,
  type ProxyProvider,
} from '../../api/proxies'
import { Card } from '../../components/ui/Card'
import { DataTable, Column } from '../../components/ui/DataTable'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Modal } from '../../components/ui/Modal'
import { Input } from '../../components/ui/Input'
import { Select } from '../../components/ui/Select'
import type { Proxy, ProxyProtocol, ProxyType } from '../../types'
import { formatDistanceToNow } from 'date-fns'

// Providers are tabs rather than one long table with a provider column: the
// pool runs to thousands of rows across sources with wildly different quality,
// and "which of these came from Webshare" is the question actually being asked.
// ALL_TAB keeps an aggregate view available alongside them.
const ALL_TAB = '__all__'

function ProviderTabs({
  providers, active, onSelect, totalAvailable, onToggle, toggling,
}: {
  providers: ProxyProvider[]
  active: string
  onSelect: (key: string) => void
  totalAvailable: number
  onToggle: (key: string, isEnabled: boolean) => void
  toggling: boolean
}) {
  return (
    <div className="flex flex-wrap items-stretch gap-1 border-b border-gray-700/60 px-2 pt-2">
      {/* Aggregate view. No switch - there is nothing to turn on or off across
          every source at once. */}
      <button
        onClick={() => onSelect(ALL_TAB)}
        className={`-mb-px rounded-t-lg border-b-2 px-3 py-2 text-sm transition-colors ${
          active === ALL_TAB
            ? 'border-brand-500 text-gray-100'
            : 'border-transparent text-gray-500 hover:text-gray-300'
        }`}
      >
        All providers
        <span className="ml-1.5 text-xs text-gray-600">{totalAvailable}</span>
      </button>

      {providers.map((provider) => {
        const selected = active === provider.key
        const off = !provider.is_enabled
        return (
          // The switch lives ON the tab, not in a panel below it: every
          // provider's state is then visible and changeable at a glance, with no
          // need to select a tab first. A div rather than a button because a
          // checkbox inside a button is invalid HTML and the two clicks fight.
          <div
            key={provider.key}
            className={`-mb-px flex items-center gap-2 rounded-t-lg border-b-2 pl-2 pr-3 transition-colors ${
              selected ? 'border-brand-500 bg-gray-800/60' : 'border-transparent hover:bg-gray-800/30'
            }`}
          >
            <input
              type="checkbox"
              checked={provider.is_enabled}
              disabled={toggling}
              onChange={(e) => onToggle(provider.key, e.target.checked)}
              title={
                provider.is_enabled
                  ? 'Used for new identities - uncheck to stop offering its proxies'
                  : 'Not used for new identities - check to start offering its proxies again'
              }
              aria-label={`Use ${provider.display_name} for new identities`}
            />
            <button
              onClick={() => onSelect(provider.key)}
              className={`py-2 text-sm transition-colors ${
                selected ? 'text-gray-100' : 'text-gray-500 hover:text-gray-300'
              } ${off ? 'line-through decoration-gray-600' : ''}`}
              title={off ? 'Switched off - not used for new identities' : 'Show only this provider'}
            >
              {provider.display_name}
              <span className={`ml-1.5 text-xs ${selected ? 'text-gray-400' : 'text-gray-600'}`}>
                {provider.available}
              </span>
            </button>
          </div>
        )
      })}
    </div>
  )
}

// Detail for whichever provider's tab is open. The on/off switch itself is on
// the tab (see ProviderTabs) - this explains what that switch does, since the
// surprising part is that nothing is deleted.
function ProviderPanel({ provider }: { provider: ProxyProvider }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-gray-700/40 px-4 py-3 text-xs text-gray-500">
      <Badge variant={provider.kind === 'paid' ? 'success' : 'gray'} label={provider.kind} />
      <span><span className="text-gray-200">{provider.available_healthy}</span> usable</span>
      <span>{provider.available} in pool</span>
      <span>{provider.retired} used</span>
      {!provider.can_fetch && provider.kind !== 'manual' && <span>not fetchable</span>}

      {provider.needs_api_key && (
        <p className="w-full text-[11px] text-amber-400">
          No credentials configured — set WEBSHARE_API_KEY (proxy list) or
          WEBSHARE_PROXY_USERNAME / WEBSHARE_PROXY_PASSWORD (rotating endpoint) in backend/.env
        </p>
      )}
      {!provider.is_enabled && (
        <p className="w-full text-[11px] text-gray-500">
          Switched off: its proxies stay in the pool and the list below still shows them, they just
          aren't offered to new identities and aren't re-fetched. Turning it back on makes them
          eligible again straight away.
        </p>
      )}
    </div>
  )
}

export default function ProxiesPage() {
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [healthFilter, setHealthFilter] = useState('')
  // Retired proxies (used by a pipeline, or retired after failing in real use)
  // are hidden by default. Their rows exist only so a later scrape can't
  // re-import the same address - they're never selectable again, and there are
  // thousands of them, so showing them by default buries the live pool.
  const [showRetired, setShowRetired] = useState(false)
  // Which provider tab is open. ALL_TAB shows every source at once.
  const [activeTab, setActiveTab] = useState<string>(ALL_TAB)
  const [newProxy, setNewProxy] = useState<Partial<Proxy>>({ host: '', port: 8080, protocol: 'http', type: 'datacenter', country: 'US', provider: 'custom' })

  const { data: proxies = [], isLoading } = useQuery({
    queryKey: ['proxies', healthFilter, showRetired, activeTab],
    queryFn: () => getProxies({
      ...(healthFilter !== '' ? { is_healthy: healthFilter } : {}),
      ...(showRetired ? {} : { retired: 'false' }),
      ...(activeTab !== ALL_TAB ? { provider: activeTab } : {}),
    }),
    refetchInterval: 15000,
  })

  const { data: providers = [], error: providersError } = useQuery({
    queryKey: ['proxies', 'providers'],
    queryFn: getProxyProviders,
    refetchInterval: 15000,
  })

  const { data: stats } = useQuery({
    queryKey: ['proxies', 'stats'],
    queryFn: getProxyStats,
    refetchInterval: 15000,
  })

  const testAllSequentially = async () => {
    // Only the live pool - re-testing retired proxies would be thousands of
    // requests to confirm something already permanently excluded.
    const allProxies = await getProxies({ retired: 'false' })
    const batchSize = 50

    for (let i = 0; i < allProxies.length; i += batchSize) {
      const batch = allProxies.slice(i, i + batchSize)
      await Promise.all(batch.map(proxy => testProxy(proxy.id)))
    }
  }

  const inv = () => qc.invalidateQueries({ queryKey: ['proxies'] })
  const del = useMutation({ mutationFn: deleteProxy, onSuccess: inv })
  const test = useMutation({ mutationFn: (id: string) => testProxy(id), onSuccess: inv })
  const testAll = useMutation({ mutationFn: testAllSequentially, onSuccess: inv })
  const cleanup = useMutation({ mutationFn: cleanupUnhealthyProxies, onSuccess: inv })
  const create = useMutation({ mutationFn: createProxy, onSuccess: () => { inv(); setShowCreate(false) } })
  const toggleProvider = useMutation({
    mutationFn: ({ key, isEnabled }: { key: string; isEnabled: boolean }) =>
      setProxyProviderEnabled(key, isEnabled),
    onSuccess: inv,
  })
  const fetchFree = useMutation({ 
    mutationFn: fetchProxiesFromFreeList, 
    onSuccess: () => { 
      inv()
      alert('Successfully fetched and imported proxies from free-proxy-list.net and proxyscrape.com!')
    },
    onError: (error: any) => {
      alert(`Error fetching proxies: ${error.message}`)
    }
  })

  const providerByKey = new Map(providers.map((provider) => [provider.key, provider]))
  const activeProvider = activeTab === ALL_TAB ? null : providerByKey.get(activeTab) ?? null

  const columns: Column<Proxy>[] = [
    { key: 'host', header: 'Address', render: (p) => <span className="font-mono text-sm text-gray-200">{p.host}:{p.port}</span> },
    { key: 'type', header: 'Type', render: (p) => <Badge variant="info" label={p.type} /> },
    { key: 'protocol', header: 'Protocol', render: (p) => <Badge variant="gray" label={p.protocol} /> },
    { key: 'country', header: 'Country', render: (p) => <span className="text-gray-400">{p.country}</span> },
    {
      key: 'provider', header: 'Provider',
      render: (p) => {
        const known = providerByKey.get(p.provider)
        return (
          <button
            onClick={() => setActiveTab(p.provider)}
            className={`text-left hover:underline ${known && !known.is_enabled ? 'text-gray-600 line-through' : 'text-gray-400'}`}
            title={known && !known.is_enabled ? 'This provider is switched off - not used for new identities' : 'Open this provider'}
          >
            {p.provider}
          </button>
        )
      },
    },
    {
      key: 'health', header: 'Health',
      render: (p) => (
        <div className="flex items-center gap-1.5">
          <div className={`h-2 w-2 rounded-full ${p.is_healthy ? 'bg-emerald-400' : 'bg-red-500'}`} />
          <span className={p.is_healthy ? 'text-emerald-400' : 'text-red-400'}>{p.is_healthy ? 'OK' : 'Down'}</span>
        </div>
      ),
    },
    {
      key: 'assigned', header: 'State',
      render: (p) => (
        p.is_rotating
          ? <span className="text-sky-400 text-xs" title="Rotating endpoint: one hostname, a different exit IP per connection - reusable across identities without any of them sharing an address">rotating</span>
          : p.consumed_at
          ? <span className="text-red-400 text-xs" title="An account was registered through this IP - retired permanently, never offered again">retired</span>
          : p.assigned_bot_id
            ? <span className="text-amber-300 text-xs" title="Reserved for an identity whose pipeline hasn't run yet">reserved</span>
            : !p.is_healthy
              ? <span className="text-amber-400 text-xs" title="Failed its check or failed in a real run - not handed to any identity. Not blacklisted: the next import replaces it and it can come back">flagged</span>
              : <span className="text-gray-500 text-xs">free</span>
      ),
    },
    { key: 'checked', header: 'Last Checked', render: (p) => <span className="text-gray-500 text-xs">{formatDistanceToNow(new Date(p.last_checked), { addSuffix: true })}</span> },
    {
      key: 'actions', header: '',
      render: (p) => (
        <div className="flex gap-1.5">
          <Button size="sm" variant="secondary" onClick={() => test.mutate(p.id)}>Test</Button>
          <Button size="sm" variant="danger" onClick={() => del.mutate(p.id)}>✕</Button>
        </div>
      ),
    },
  ]

  return (
    <div className="space-y-5">
      {/* Counted in the database (GET /api/proxies/stats) rather than from the
          rows on screen - the retired set runs to thousands and is never
          fetched. */}
      <div className="grid grid-cols-4 gap-4">
        <div className="rounded-xl border border-gray-700/60 bg-gray-800/40 px-5 py-4">
          <p className="text-2xl font-bold text-gray-200">{stats?.available ?? 0}</p>
          <p className="text-xs text-gray-500 mt-0.5">In the pool</p>
        </div>
        <div className="rounded-xl border border-gray-700/60 bg-gray-800/40 px-5 py-4">
          <p className="text-2xl font-bold text-emerald-400">{stats?.available_healthy ?? 0}</p>
          <p className="text-xs text-gray-500 mt-0.5">Healthy</p>
        </div>
        <div className="rounded-xl border border-gray-700/60 bg-gray-800/40 px-5 py-4">
          <p className="text-2xl font-bold text-amber-400">{(stats?.available ?? 0) - (stats?.available_healthy ?? 0)}</p>
          <p className="text-xs text-gray-500 mt-0.5">Flagged — replaced next import</p>
        </div>
        <div className="rounded-xl border border-gray-700/60 bg-gray-800/40 px-5 py-4">
          <p className="text-2xl font-bold text-red-400">{stats?.retired ?? 0}</p>
          <p className="text-xs text-gray-500 mt-0.5">Used — never reused</p>
        </div>
      </div>

      <Card noPad title="Proxies">
        <ProviderTabs
          providers={providers}
          active={activeTab}
          onSelect={setActiveTab}
          totalAvailable={stats?.available ?? 0}
          onToggle={(key, isEnabled) => toggleProvider.mutate({ key, isEnabled })}
          toggling={toggleProvider.isPending}
        />
        {/* An empty provider list used to look identical to a backend that
            doesn't serve /api/proxies/providers yet - which is exactly what a
            stale running server looks like. Say which it is. */}
        {providersError && (
          <p className="border-b border-amber-700/40 bg-amber-900/10 px-4 py-2.5 text-xs text-amber-300">
            Couldn't load providers: {providersError instanceof Error ? providersError.message : 'request failed'}.
            If the backend is running an older build, restart it — the per-provider switches need
            GET /api/proxies/providers.
          </p>
        )}
        {activeProvider && <ProviderPanel provider={activeProvider} />}
        <div className="flex flex-wrap items-center justify-end gap-2 px-4 py-3">

            <select
              value={healthFilter}
              onChange={(e) => setHealthFilter(e.target.value)}
              className="rounded-lg border border-gray-600 bg-gray-800 px-3 py-1.5 text-sm text-gray-300 focus:outline-none"
            >
              <option value="">All Health</option>
              <option value="true">Healthy</option>
              <option value="false">Down</option>
            </select>
            <label className="flex items-center gap-1.5 text-sm text-gray-400 whitespace-nowrap px-1">
              <input type="checkbox" checked={showRetired} onChange={(e) => setShowRetired(e.target.checked)} />
              Show retired
            </label>
            <Button variant="secondary" loading={testAll.isPending} onClick={() => testAll.mutate()}>Test All</Button>
            <Button variant="danger" loading={cleanup.isPending} onClick={() => cleanup.mutate()}>Cleanup</Button>
            <Button variant="primary" loading={fetchFree.isPending} onClick={() => fetchFree.mutate()}>Get Proxies</Button>
            <Button onClick={() => setShowCreate(true)}>+ Add Proxy</Button>
        </div>
        <DataTable columns={columns} data={proxies} keyExtractor={(p) => p.id} loading={isLoading} emptyMessage="No proxies — add one to get started" />
      </Card>

      <Modal title="Add Proxy" isOpen={showCreate} onClose={() => setShowCreate(false)}
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button loading={create.isPending} onClick={() => create.mutate(newProxy)}>Add</Button>
          </div>
        }
      >
        <div className="space-y-4">
          <Input label="Host" value={newProxy.host} onChange={(e) => setNewProxy(n => ({ ...n, host: e.target.value }))} placeholder="192.168.1.1" />
          <Input label="Port" type="number" value={newProxy.port} onChange={(e) => setNewProxy(n => ({ ...n, port: +e.target.value }))} />
          <Select label="Protocol" value={newProxy.protocol} onChange={(e) => setNewProxy(n => ({ ...n, protocol: e.target.value as ProxyProtocol }))} options={[{value:'http',label:'HTTP'},{value:'socks5',label:'SOCKS5'}]} />
          <Select label="Type" value={newProxy.type} onChange={(e) => setNewProxy(n => ({ ...n, type: e.target.value as ProxyType }))} options={[{value:'datacenter',label:'Datacenter'},{value:'residential',label:'Residential'},{value:'mobile',label:'Mobile'}]} />
          <Input label="Country Code" value={newProxy.country} onChange={(e) => setNewProxy(n => ({ ...n, country: e.target.value }))} placeholder="US" />
          <Input label="Provider" value={newProxy.provider} onChange={(e) => setNewProxy(n => ({ ...n, provider: e.target.value }))} placeholder="oxylabs" />
        </div>
      </Modal>
    </div>
  )
}
