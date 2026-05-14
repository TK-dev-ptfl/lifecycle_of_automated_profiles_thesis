import { ReactNode } from 'react'
import { clsx } from 'clsx'

interface KpiCardProps {
  value: string | number
  label: string
  trend?: 'up' | 'down' | 'neutral'
  trendValue?: string
  icon?: ReactNode
  color?: 'blue' | 'green' | 'red' | 'amber' | 'purple'
}

const colors = {
  blue: 'text-blue-400 bg-blue-900/30',
  green: 'text-emerald-400 bg-emerald-900/30',
  red: 'text-red-400 bg-red-900/30',
  amber: 'text-amber-400 bg-amber-900/30',
  purple: 'text-purple-400 bg-purple-900/30',
}

export function KpiCard({ value, label, trend, trendValue, icon, color = 'blue' }: KpiCardProps) {
  return (
    <div className="rounded-xl border border-gray-700/60 bg-gray-800/50 p-5 flex items-start gap-4">
      {icon && (
        <div className={clsx('rounded-lg p-2.5', colors[color])}>
          <div className="h-5 w-5">{icon}</div>
        </div>
      )}
      <div className="min-w-0 flex-1">
        <p className="text-2xl font-bold text-gray-100 tabular-nums">{value}</p>
        <p className="mt-0.5 text-xs text-gray-500">{label}</p>
        {trendValue && (
          <p className={clsx('mt-1 text-xs font-medium',
            trend === 'up' ? 'text-emerald-400' : trend === 'down' ? 'text-red-400' : 'text-gray-400'
          )}>
            {trend === 'up' ? '↑' : trend === 'down' ? '↓' : '→'} {trendValue}
          </p>
        )}
      </div>
    </div>
  )
}
