import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import LoginPage from '../pages/Login'
import FleetPage from '../pages/Fleet'
import TasksPage from '../pages/Tasks'
import MonitoringPage from '../pages/Monitoring'

// Mock stores
vi.mock('../stores/authStore', () => ({
  useAuthStore: vi.fn((selector: any) => {
    const state = { isAuthenticated: true, username: 'admin', login: vi.fn(), logout: vi.fn() }
    return selector ? selector(state) : state
  }),
}))

// Mock APIs
vi.mock('../api/bots', () => ({
  getBots: vi.fn().mockResolvedValue([
    { id: '1', name: 'TestBot', status: 'running', mode: 'growing', skeleton: 'engagement_farmer', flag_count: 0, last_active: new Date().toISOString(), created_at: new Date().toISOString(), updated_at: new Date().toISOString(), platform_id: 'p1', parameters: {}, algorithm_config: {}, communication_mode: 'official_api', behaviour_pattern: 'passive' },
  ]),
  runBot: vi.fn().mockResolvedValue({ id: '1', status: 'running' }),
  pauseBot: vi.fn().mockResolvedValue({ id: '1', status: 'paused' }),
  stopBot: vi.fn().mockResolvedValue({ id: '1', status: 'stopped' }),
  deleteBot: vi.fn().mockResolvedValue(undefined),
  createBot: vi.fn().mockResolvedValue({ id: '2', name: 'NewBot', status: 'stopped' }),
}))

vi.mock('../api/tasks', () => ({
  getTasks: vi.fn().mockResolvedValue([
    { id: 't1', name: 'Task 1', type: 'scrape', status: 'idle', concurrency: 1, result_count: 0, error_count: 0, created_at: new Date().toISOString(), platform_id: 'p1', payload: {}, schedule: {}, sync_mode: 'independent', success_criteria: {} },
  ]),
  createTask: vi.fn().mockResolvedValue({ id: 't2', name: 'New Task' }),
  deleteTask: vi.fn().mockResolvedValue(undefined),
  runTask: vi.fn().mockResolvedValue({ id: 't1', status: 'running' }),
  pauseTask: vi.fn().mockResolvedValue({ id: 't1', status: 'paused' }),
  stopTask: vi.fn().mockResolvedValue({ id: 't1', status: 'failed' }),
}))

vi.mock('../api/platforms', () => ({
  getPlatforms: vi.fn().mockResolvedValue([
    { id: 'p1', name: 'reddit', display_name: 'Reddit', is_enabled: true, rate_limits: {}, adapter_config: {}, created_at: new Date().toISOString() },
  ]),
  getFleetSummary: vi.fn().mockResolvedValue({
    total: 5, by_status: { running: 2, paused: 1, stopped: 1, flagged: 1, banned: 0 }, by_mode: { growing: 2, trust: 1, executing: 1, maintaining: 1 }
  }),
  getFleetHealth: vi.fn().mockResolvedValue([
    { id: '1', name: 'Bot1', status: 'running', mode: 'growing', flag_count: 0, last_active: new Date().toISOString() },
  ]),
}))

const createWrapper = () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        {children}
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('LoginPage', () => {
  it('renders login form', () => {
    const qc = new QueryClient()
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <LoginPage />
        </MemoryRouter>
      </QueryClientProvider>
    )
    expect(screen.getByText('Sign in')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('admin')).toBeInTheDocument()
  })
})

describe('FleetPage', () => {
  it('renders fleet page with bots', async () => {
    const Wrapper = createWrapper()
    render(<Wrapper><FleetPage /></Wrapper>)
    await waitFor(() => {
      expect(screen.getByText('TestBot')).toBeInTheDocument()
    })
  })

  it('renders summary stats', async () => {
    const Wrapper = createWrapper()
    render(<Wrapper><FleetPage /></Wrapper>)
    await waitFor(() => {
      expect(screen.getByText('Total Bots')).toBeInTheDocument()
    })
  })

  it('shows new bot button', async () => {
    const Wrapper = createWrapper()
    render(<Wrapper><FleetPage /></Wrapper>)
    expect(screen.getByText('+ New Bot')).toBeInTheDocument()
  })

  it('opens create modal when New Bot clicked', async () => {
    const Wrapper = createWrapper()
    render(<Wrapper><FleetPage /></Wrapper>)
    fireEvent.click(screen.getByText('+ New Bot'))
    await waitFor(() => {
      expect(screen.getByText('Create New Bot')).toBeInTheDocument()
    })
  })
})

describe('TasksPage', () => {
  it('renders tasks', async () => {
    const Wrapper = createWrapper()
    render(<Wrapper><TasksPage /></Wrapper>)
    await waitFor(() => {
      expect(screen.getByText('Task 1')).toBeInTheDocument()
    })
  })

  it('shows new task button', () => {
    const Wrapper = createWrapper()
    render(<Wrapper><TasksPage /></Wrapper>)
    expect(screen.getByText('+ New Task')).toBeInTheDocument()
  })

  it('shows task stats', async () => {
    const Wrapper = createWrapper()
    render(<Wrapper><TasksPage /></Wrapper>)
    await waitFor(() => {
      expect(screen.getByText('Total Tasks')).toBeInTheDocument()
      expect(screen.getByText('Running')).toBeInTheDocument()
    })
  })
})

describe('MonitoringPage', () => {
  it('renders monitoring page', async () => {
    const Wrapper = createWrapper()
    render(<Wrapper><MonitoringPage /></Wrapper>)
    await waitFor(() => {
      expect(screen.getByText('Total Bots')).toBeInTheDocument()
    })
  })

  it('shows fleet health', async () => {
    const Wrapper = createWrapper()
    render(<Wrapper><MonitoringPage /></Wrapper>)
    await waitFor(() => {
      expect(screen.getByText('Fleet Health')).toBeInTheDocument()
    })
  })
})
