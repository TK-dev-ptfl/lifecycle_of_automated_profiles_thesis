import { useQuery } from '@tanstack/react-query'
import { getFleetSummary, getFleetHealth } from '../../api/platforms'
import { KpiCard } from '../../components/ui/KpiCard'
import { Card } from '../../components/ui/Card'
import { StatusDot } from '../../components/ui/StatusDot'
import { Badge } from '../../components/ui/Badge'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid } from 'recharts'
import type { BotStatus } from '../../types'
import { formatDistanceToNow } from 'date-fns'

const COLORS = ['#4f6ef7','#10b981','#f59e0b','#ef4444','#8b5cf6']

const mockLineData = Array.from({ length: 24 }, (_, i) => ({
  hour: `${i}:00`,
  actions: Math.floor(Math.random() * 80 + 10),
  success_rate: Math.random() * 0.3 + 0.7,
}))

export default function MonitoringPage() {
  const { data: summary } = useQuery({ queryKey: ['fleet-summary'], queryFn: getFleetSummary, refetchInterval: 10000 })
  const { data: health = [] } = useQuery({ queryKey: ['fleet-health'], queryFn: getFleetHealth, refetchInterval: 10000 })

  const pieData = summary ? Object.entries(summary.by_status).map(([k, v]) => ({ name: k, value: v })) : []
  const modePieData = summary ? Object.entries(summary.by_mode).map(([k, v]) => ({ name: k, value: v })) : []

  return (
    <div className="space-y-5">
      {/* KPIs */}
      <div className="grid grid-cols-4 gap-4">
        <KpiCard value={summary?.total ?? 0} label="Total Bots" color="blue" />
        <KpiCard value={summary?.by_status?.running ?? 0} label="Running" color="green" />
        <KpiCard value={(summary?.by_status?.flagged ?? 0) + (summary?.by_status?.banned ?? 0)} label="Flagged/Banned" color="red" />
        <KpiCard value={`${((((summary?.by_status?.running ?? 0) / Math.max(summary?.total ?? 1, 1)) * 100)).toFixed(0)}%`} label="Uptime Rate" color="purple" />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-3 gap-5">
        <Card title="Status Distribution" className="col-span-1">
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie data={pieData} cx="50%" cy="50%" innerRadius={50} outerRadius={80} dataKey="value" nameKey="name">
                {pieData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8, color: '#f3f4f6' }} />
            </PieChart>
          </ResponsiveContainer>
          <div className="flex flex-wrap gap-2 justify-center mt-2">
            {pieData.map((d, i) => (
              <div key={d.name} className="flex items-center gap-1.5 text-xs">
                <div className="h-2 w-2 rounded-full" style={{ background: COLORS[i % COLORS.length] }} />
                <span className="text-gray-400">{d.name}: {d.value}</span>
              </div>
            ))}
          </div>
        </Card>

        <Card title="Actions per Hour (24h)" className="col-span-2">
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={mockLineData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="hour" tick={{ fill: '#6b7280', fontSize: 10 }} interval={3} />
              <YAxis tick={{ fill: '#6b7280', fontSize: 10 }} />
              <Tooltip contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8, color: '#f3f4f6' }} />
              <Line type="monotone" dataKey="actions" stroke="#4f6ef7" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </Card>
      </div>

      {/* Fleet health grid */}
      <Card title="Fleet Health">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
          {health.map((bot) => (
            <div
              key={bot.id}
              className={`rounded-lg border p-3 transition-colors ${
                bot.status === 'running' ? 'border-emerald-700/50 bg-emerald-900/10' :
                bot.status === 'flagged' || bot.status === 'banned' ? 'border-red-700/50 bg-red-900/10' :
                'border-gray-700/50 bg-gray-800/30'
              }`}
            >
              <div className="flex items-center gap-2 mb-2">
                <StatusDot status={bot.status as BotStatus} />
                <span className="text-sm font-medium text-gray-200 truncate">{bot.name}</span>
              </div>
              <div className="flex justify-between text-xs">
                <Badge variant={bot.mode === 'executing' ? 'success' : 'gray'} label={bot.mode} />
                {bot.flag_count > 0 && <span className="text-red-400">{bot.flag_count} flags</span>}
              </div>
              <p className="text-xs text-gray-600 mt-1.5">
                {bot.last_active ? formatDistanceToNow(new Date(bot.last_active), { addSuffix: true }) : '—'}
              </p>
            </div>
          ))}
          {health.length === 0 && (
            <p className="col-span-full text-center text-gray-600 py-6">No bots to monitor</p>
          )}
        </div>
      </Card>
    </div>
  )
}
