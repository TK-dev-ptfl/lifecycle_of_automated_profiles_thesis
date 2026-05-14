import { useLocation } from 'react-router-dom'
import { useAuthStore } from '../../stores/authStore'
import { Button } from '../ui/Button'

const titles: Record<string, string> = {
  '/fleet': 'Fleet Overview',
  '/tasks': 'Tasks',
  '/monitoring': 'Monitoring',
  '/identities': 'Identities',
  '/proxies': 'Proxies',
  '/platforms': 'Platforms',
  '/algorithm': 'Algorithm',
  '/lifecycle': 'Lifecycle',
  '/simulation': 'Simulation',
  '/settings': 'Settings',
}

export function Topbar() {
  const { pathname } = useLocation()
  const logout = useAuthStore((s) => s.logout)
  const base = '/' + pathname.split('/')[1]
  const title = titles[base] ?? 'Dashboard'

  return (
    <header className="flex h-14 items-center justify-between border-b border-gray-700/50 bg-gray-900/80 backdrop-blur-sm px-6">
      <h1 className="text-sm font-semibold text-gray-200">{title}</h1>
      <div className="flex items-center gap-3">
        <div className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" title="Connected" />
        <Button variant="ghost" size="sm" onClick={logout}>
          Sign out
        </Button>
      </div>
    </header>
  )
}
