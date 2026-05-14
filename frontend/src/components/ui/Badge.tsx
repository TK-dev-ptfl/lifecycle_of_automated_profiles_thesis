import { clsx } from 'clsx'

type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'gray' | 'purple'

interface BadgeProps {
  variant?: BadgeVariant
  label: string
  className?: string
}

const variants: Record<BadgeVariant, string> = {
  success: 'bg-emerald-900/60 text-emerald-300 ring-1 ring-emerald-700/50',
  warning: 'bg-amber-900/60 text-amber-300 ring-1 ring-amber-700/50',
  danger: 'bg-red-900/60 text-red-300 ring-1 ring-red-700/50',
  info: 'bg-blue-900/60 text-blue-300 ring-1 ring-blue-700/50',
  gray: 'bg-gray-800 text-gray-400 ring-1 ring-gray-700',
  purple: 'bg-purple-900/60 text-purple-300 ring-1 ring-purple-700/50',
}

export function Badge({ variant = 'gray', label, className }: BadgeProps) {
  return (
    <span className={clsx('inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium', variants[variant], className)}>
      {label}
    </span>
  )
}
