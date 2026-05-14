import { clsx } from 'clsx'
import type { BotStatus } from '../../types'

const colors: Record<BotStatus, string> = {
  running: 'bg-emerald-400 shadow-[0_0_6px_2px_rgba(52,211,153,0.4)]',
  paused: 'bg-amber-400',
  stopped: 'bg-gray-500',
  flagged: 'bg-orange-400',
  banned: 'bg-red-500',
}

interface StatusDotProps {
  status: BotStatus
  className?: string
}

export function StatusDot({ status, className }: StatusDotProps) {
  return (
    <span
      className={clsx(
        'inline-block h-2 w-2 rounded-full flex-shrink-0',
        colors[status],
        status === 'running' && 'animate-pulse',
        className
      )}
    />
  )
}
