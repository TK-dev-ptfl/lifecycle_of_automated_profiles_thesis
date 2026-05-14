import { ReactNode } from 'react'

interface PageShellProps {
  children: ReactNode
}

export function PageShell({ children }: PageShellProps) {
  return (
    <main className="flex-1 overflow-y-auto bg-gray-950 p-6">
      {children}
    </main>
  )
}
