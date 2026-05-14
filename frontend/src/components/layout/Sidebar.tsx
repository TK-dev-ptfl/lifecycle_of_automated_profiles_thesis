import { NavLink } from 'react-router-dom'
import { clsx } from 'clsx'

const navItems = [
  {
    group: 'Operations',
    items: [
      { to: '/fleet', label: 'Fleet', icon: '⚡' },
      { to: '/tasks', label: 'Tasks', icon: '📋' },
      { to: '/monitoring', label: 'Monitoring', icon: '📊' },
    ],
  },
  {
    group: 'Resources',
    items: [
      { to: '/identities', label: 'Identities', icon: '👤' },
      { to: '/proxies', label: 'Proxies', icon: '🔌' },
      { to: '/emails', label: 'Emails', icon: '✉️' },
    ],
  },
  {
    group: 'Advanced',
    items: [
      { to: '/algorithm', label: 'Algorithm', icon: '🧠' },
      { to: '/pipelines', label: 'Pipelines', icon: '�' },
      { to: '/sandboxes', label: 'Sandboxes', icon: '🧪' },
    ],
  },
  {
    group: 'System',
    items: [
      { to: '/settings', label: 'Settings', icon: '⚙️' },
    ],
  },
]

export function Sidebar() {
  return (
    <aside className="flex h-screen w-56 flex-col border-r border-gray-700/50 bg-gray-900">
      <div className="flex items-center gap-2.5 px-5 py-5 border-b border-gray-700/50">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-500 text-sm font-bold text-white">B</div>
        <span className="text-sm font-semibold text-gray-100">BotDash</span>
      </div>

      <nav className="flex-1 overflow-y-auto py-3 px-3 space-y-5">
        {navItems.map((group) => (
          <div key={group.group}>
            <p className="mb-1 px-2 text-xs font-semibold uppercase tracking-wider text-gray-600">
              {group.group}
            </p>
            <div className="space-y-0.5">
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    clsx(
                      'flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition-colors',
                      isActive
                        ? 'bg-brand-500/15 text-brand-400'
                        : 'text-gray-500 hover:bg-gray-800 hover:text-gray-300'
                    )
                  }
                >
                  <span className="text-base leading-none">{item.icon}</span>
                  {item.label}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>

      <div className="border-t border-gray-700/50 px-3 py-3">
        <div className="flex items-center gap-2.5 rounded-lg px-2.5 py-2">
          <div className="h-7 w-7 rounded-full bg-gradient-to-br from-brand-500 to-purple-600 flex items-center justify-center text-xs font-bold text-white">
            A
          </div>
          <div className="min-w-0">
            <p className="truncate text-xs font-medium text-gray-300">admin</p>
            <p className="text-xs text-gray-600">Operator</p>
          </div>
        </div>
      </div>
    </aside>
  )
}

