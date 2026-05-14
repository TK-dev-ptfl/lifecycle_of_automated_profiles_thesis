import { ReactNode } from 'react'
import { clsx } from 'clsx'

interface CardProps {
  title?: string
  children: ReactNode
  action?: ReactNode
  className?: string
  noPad?: boolean
}

export function Card({ title, children, action, className, noPad }: CardProps) {
  return (
    <div className={clsx('rounded-xl border border-gray-700/60 bg-gray-800/50 backdrop-blur-sm', className)}>
      {(title || action) && (
        <div className="flex items-center justify-between border-b border-gray-700/50 px-5 py-3.5">
          {title && <h3 className="text-sm font-semibold text-gray-200">{title}</h3>}
          {action && <div>{action}</div>}
        </div>
      )}
      <div className={noPad ? '' : 'p-5'}>{children}</div>
    </div>
  )
}
