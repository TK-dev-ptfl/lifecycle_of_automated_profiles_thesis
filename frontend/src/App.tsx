import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuthStore } from './stores/authStore'
import { Sidebar } from './components/layout/Sidebar'
import { Topbar } from './components/layout/Topbar'
import { PageShell } from './components/layout/PageShell'
import LoginPage from './pages/Login'
import FleetPage from './pages/Fleet'
import BotDetailPage from './pages/BotDetail'
import TasksPage from './pages/Tasks'
import IdentitiesPage from './pages/Identities'
import ProxiesPage from './pages/Proxies'
import MonitoringPage from './pages/Monitoring'
import AlgorithmPage from './pages/Algorithm'
import PipelinesPage from './pages/Pipelines'
import EmailsPage from './pages/Emails'
import SandboxesPage from './pages/Sandboxes'
import SettingsPage from './pages/Settings'

function ProtectedLayout() {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Topbar />
        <PageShell>
          <Routes>
            <Route index element={<Navigate to="/fleet" replace />} />
            <Route path="fleet" element={<FleetPage />} />
            <Route path="bots/:id" element={<BotDetailPage />} />
            <Route path="tasks" element={<TasksPage />} />
            <Route path="identities" element={<IdentitiesPage />} />
            <Route path="proxies" element={<ProxiesPage />} />
            <Route path="monitoring" element={<MonitoringPage />} />
            <Route path="algorithm" element={<AlgorithmPage />} />
            <Route path="pipelines" element={<PipelinesPage />} />
            <Route path="emails" element={<EmailsPage />} />
            <Route path="sandboxes" element={<SandboxesPage />} />
            <Route path="settings" element={<SettingsPage />} />
          </Routes>
        </PageShell>
      </div>
    </div>
  )
}

export default function App() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)

  return (
    <Routes>
      <Route path="/login" element={isAuthenticated ? <Navigate to="/fleet" replace /> : <LoginPage />} />
      <Route
        path="/*"
        element={isAuthenticated ? <ProtectedLayout /> : <Navigate to="/login" replace />}
      />
    </Routes>
  )
}
