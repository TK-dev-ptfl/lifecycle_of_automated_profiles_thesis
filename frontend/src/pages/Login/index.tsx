import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../stores/authStore'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'

export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const login = useAuthStore((s) => s.login)
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(username, password)
      navigate('/fleet')
    } catch {
      setError('Invalid username or password')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="flex items-center justify-center gap-3 mb-8">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-500 text-lg font-bold text-white shadow-lg shadow-brand-500/30">
            B
          </div>
          <div>
            <h1 className="text-lg font-bold text-gray-100">BotDash</h1>
            <p className="text-xs text-gray-500">Management Dashboard</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="rounded-2xl border border-gray-700/60 bg-gray-800/50 backdrop-blur-sm p-8 space-y-4 shadow-xl">
          <div className="text-center mb-2">
            <h2 className="text-base font-semibold text-gray-200">Sign in</h2>
            <p className="text-xs text-gray-500 mt-1">Default: admin / admin123</p>
          </div>

          {error && (
            <div className="rounded-lg border border-red-700/50 bg-red-900/20 px-3 py-2 text-sm text-red-400">
              {error}
            </div>
          )}

          <Input
            label="Username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="admin"
            autoComplete="username"
          />
          <Input
            label="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            autoComplete="current-password"
          />

          <Button type="submit" className="w-full justify-center" loading={loading}>
            Sign In
          </Button>
        </form>
      </div>
    </div>
  )
}
