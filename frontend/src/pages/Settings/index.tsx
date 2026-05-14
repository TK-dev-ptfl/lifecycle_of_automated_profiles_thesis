import { useState } from 'react'
import { Card } from '../../components/ui/Card'
import { Input } from '../../components/ui/Input'
import { Button } from '../../components/ui/Button'

export default function SettingsPage() {
  const [password, setPassword] = useState({ current: '', next: '', confirm: '' })
  const [alerts, setAlerts] = useState({ telegram_token: '', chat_id: '', email_enabled: false })
  const [saved, setSaved] = useState(false)

  const save = () => { setSaved(true); setTimeout(() => setSaved(false), 2000) }

  return (
    <div className="space-y-5 max-w-2xl">
      <Card title="Account">
        <div className="space-y-4">
          <Input label="Current Password" type="password" value={password.current} onChange={(e) => setPassword(p => ({ ...p, current: e.target.value }))} />
          <Input label="New Password" type="password" value={password.next} onChange={(e) => setPassword(p => ({ ...p, next: e.target.value }))} />
          <Input label="Confirm Password" type="password" value={password.confirm} onChange={(e) => setPassword(p => ({ ...p, confirm: e.target.value }))} />
          <Button onClick={save} loading={false}>Update Password</Button>
        </div>
      </Card>

      <Card title="Alert Configuration">
        <div className="space-y-4">
          <Input label="Telegram Bot Token" value={alerts.telegram_token} onChange={(e) => setAlerts(a => ({ ...a, telegram_token: e.target.value }))} placeholder="123456:ABC-DEF..." />
          <Input label="Telegram Chat ID" value={alerts.chat_id} onChange={(e) => setAlerts(a => ({ ...a, chat_id: e.target.value }))} placeholder="-100123456789" />
          <div className="flex items-center gap-3">
            <input
              type="checkbox"
              id="email-alerts"
              checked={alerts.email_enabled}
              onChange={(e) => setAlerts(a => ({ ...a, email_enabled: e.target.checked }))}
              className="h-4 w-4 rounded border-gray-600 bg-gray-700 text-brand-500 focus:ring-brand-500"
            />
            <label htmlFor="email-alerts" className="text-sm text-gray-300">Enable email alerts</label>
          </div>
          <Button onClick={save}>{saved ? '✓ Saved' : 'Save Alerts'}</Button>
        </div>
      </Card>

      <Card title="System Info">
        <div className="space-y-2 text-sm">
          {[
            { label: 'Version', value: '1.0.0' },
            { label: 'Environment', value: 'Development' },
            { label: 'API URL', value: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000' },
          ].map((item) => (
            <div key={item.label} className="flex justify-between py-1.5 border-b border-gray-700/40 last:border-0">
              <span className="text-gray-500">{item.label}</span>
              <span className="text-gray-300 font-mono text-xs">{item.value}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}
