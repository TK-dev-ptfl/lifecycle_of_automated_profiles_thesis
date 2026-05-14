import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getProxies, createProxy, deleteProxy, testProxy, cleanupUnhealthyProxies, fetchProxiesFromFreeList } from '../../api/proxies'
import { Card } from '../../components/ui/Card'
import { DataTable, Column } from '../../components/ui/DataTable'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Modal } from '../../components/ui/Modal'
import { Input } from '../../components/ui/Input'
import { Select } from '../../components/ui/Select'
import type { Proxy, ProxyProtocol, ProxyType } from '../../types'
import { formatDistanceToNow } from 'date-fns'

export default function ProxiesPage() {
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [healthFilter, setHealthFilter] = useState('')
  const [newProxy, setNewProxy] = useState<Partial<Proxy>>({ host: '', port: 8080, protocol: 'http', type: 'datacenter', country: 'US', provider: 'custom' })

  const { data: proxies = [], isLoading } = useQuery({
    queryKey: ['proxies', healthFilter],
    queryFn: () => getProxies(healthFilter !== '' ? { is_healthy: healthFilter } : {}),
    refetchInterval: 15000,
  })

  const testAllSequentially = async () => {
    const allProxies = await getProxies()
    const batchSize = 50

    for (let i = 0; i < allProxies.length; i += batchSize) {
      const batch = allProxies.slice(i, i + batchSize)
      await Promise.all(batch.map(proxy => testProxy(proxy.id)))
    }
  }

  const inv = () => qc.invalidateQueries({ queryKey: ['proxies'] })
  const del = useMutation({ mutationFn: deleteProxy, onSuccess: inv })
  const test = useMutation({ mutationFn: testProxy, onSuccess: inv })
  const testAll = useMutation({ mutationFn: testAllSequentially, onSuccess: inv })
  const cleanup = useMutation({ mutationFn: cleanupUnhealthyProxies, onSuccess: inv })
  const create = useMutation({ mutationFn: createProxy, onSuccess: () => { inv(); setShowCreate(false) } })
  const fetchFree = useMutation({ 
    mutationFn: fetchProxiesFromFreeList, 
    onSuccess: () => { 
      inv()
      alert('Successfully fetched and imported proxies from free-proxy-list.net!')
    },
    onError: (error: any) => {
      alert(`Error fetching proxies: ${error.message}`)
    }
  })

  const columns: Column<Proxy>[] = [
    { key: 'host', header: 'Address', render: (p) => <span className="font-mono text-sm text-gray-200">{p.host}:{p.port}</span> },
    { key: 'type', header: 'Type', render: (p) => <Badge variant="info" label={p.type} /> },
    { key: 'protocol', header: 'Protocol', render: (p) => <Badge variant="gray" label={p.protocol} /> },
    { key: 'country', header: 'Country', render: (p) => <span className="text-gray-400">{p.country}</span> },
    { key: 'provider', header: 'Provider', render: (p) => <span className="text-gray-400">{p.provider}</span> },
    {
      key: 'health', header: 'Health',
      render: (p) => (
        <div className="flex items-center gap-1.5">
          <div className={`h-2 w-2 rounded-full ${p.is_healthy ? 'bg-emerald-400' : 'bg-red-500'}`} />
          <span className={p.is_healthy ? 'text-emerald-400' : 'text-red-400'}>{p.is_healthy ? 'OK' : 'Down'}</span>
        </div>
      ),
    },
    { key: 'assigned', header: 'Assigned', render: (p) => <span className="text-gray-500 text-xs">{p.assigned_bot_id ? '✓ Assigned' : '—'}</span> },
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

  const healthy = proxies.filter(p => p.is_healthy).length

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-3 gap-4">
        <div className="rounded-xl border border-gray-700/60 bg-gray-800/40 px-5 py-4">
          <p className="text-2xl font-bold text-gray-200">{proxies.length}</p>
          <p className="text-xs text-gray-500 mt-0.5">Total Proxies</p>
        </div>
        <div className="rounded-xl border border-gray-700/60 bg-gray-800/40 px-5 py-4">
          <p className="text-2xl font-bold text-emerald-400">{healthy}</p>
          <p className="text-xs text-gray-500 mt-0.5">Healthy</p>
        </div>
        <div className="rounded-xl border border-gray-700/60 bg-gray-800/40 px-5 py-4">
          <p className="text-2xl font-bold text-red-400">{proxies.length - healthy}</p>
          <p className="text-xs text-gray-500 mt-0.5">Down</p>
        </div>
      </div>

      <Card noPad title="Proxies"
        action={
          <div className="flex gap-2">
            <select
              value={healthFilter}
              onChange={(e) => setHealthFilter(e.target.value)}
              className="rounded-lg border border-gray-600 bg-gray-800 px-3 py-1.5 text-sm text-gray-300 focus:outline-none"
            >
              <option value="">All Health</option>
              <option value="true">Healthy</option>
              <option value="false">Down</option>
            </select>
            <Button variant="secondary" loading={testAll.isPending} onClick={() => testAll.mutate()}>Test All</Button>
            <Button variant="danger" loading={cleanup.isPending} onClick={() => cleanup.mutate()}>Cleanup</Button>
            <Button variant="primary" loading={fetchFree.isPending} onClick={() => fetchFree.mutate()}>Get Proxies</Button>
            <Button onClick={() => setShowCreate(true)}>+ Add Proxy</Button>
          </div>
        }
      >
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
