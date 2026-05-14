import { describe, it, expect, beforeEach, vi } from 'vitest'
import { act } from '@testing-library/react'
import { useFleetStore } from '../stores/fleetStore'
import { useAuthStore } from '../stores/authStore'

// Mock API
vi.mock('../api/bots', () => ({
  getBots: vi.fn().mockResolvedValue([
    { id: '1', name: 'Bot1', status: 'running', mode: 'growing', flag_count: 0, last_active: new Date().toISOString() },
    { id: '2', name: 'Bot2', status: 'stopped', mode: 'trust', flag_count: 2, last_active: new Date().toISOString() },
  ]),
}))

vi.mock('../api/auth', () => ({
  login: vi.fn().mockResolvedValue({ access_token: 'test-token', refresh_token: 'refresh-token', token_type: 'bearer' }),
  logout: vi.fn().mockResolvedValue({}),
}))

describe('useFleetStore', () => {
  beforeEach(() => {
    useFleetStore.setState({ bots: [], filters: { status: '', mode: '', platform_id: '' }, selectedBotIds: [], loading: false })
  })

  it('fetches bots', async () => {
    await act(() => useFleetStore.getState().fetchBots())
    expect(useFleetStore.getState().bots).toHaveLength(2)
  })

  it('updates bot status', () => {
    useFleetStore.setState({ bots: [{ id: '1', name: 'Bot1', status: 'running' } as any] })
    useFleetStore.getState().updateBotStatus('1', 'paused')
    expect(useFleetStore.getState().bots[0].status).toBe('paused')
  })

  it('sets bot mode', () => {
    useFleetStore.setState({ bots: [{ id: '1', name: 'Bot1', mode: 'growing' } as any] })
    useFleetStore.getState().setBotMode('1', 'executing')
    expect(useFleetStore.getState().bots[0].mode).toBe('executing')
  })

  it('toggles selection', () => {
    useFleetStore.setState({ bots: [{ id: '1' } as any, { id: '2' } as any] })
    useFleetStore.getState().toggleSelect('1')
    expect(useFleetStore.getState().selectedBotIds).toContain('1')
    useFleetStore.getState().toggleSelect('1')
    expect(useFleetStore.getState().selectedBotIds).not.toContain('1')
  })

  it('selects all bots', () => {
    useFleetStore.setState({ bots: [{ id: '1' } as any, { id: '2' } as any] })
    useFleetStore.getState().selectAll()
    expect(useFleetStore.getState().selectedBotIds).toEqual(['1', '2'])
  })

  it('clears selection', () => {
    useFleetStore.setState({ selectedBotIds: ['1', '2'] })
    useFleetStore.getState().clearSelection()
    expect(useFleetStore.getState().selectedBotIds).toHaveLength(0)
  })
})

describe('useAuthStore', () => {
  beforeEach(() => {
    localStorage.clear()
    useAuthStore.setState({ isAuthenticated: false, username: null })
  })

  it('logs in and stores tokens', async () => {
    await act(() => useAuthStore.getState().login('admin', 'admin123'))
    expect(localStorage.getItem('access_token')).toBe('test-token')
    expect(useAuthStore.getState().isAuthenticated).toBe(true)
    expect(useAuthStore.getState().username).toBe('admin')
  })

  it('logs out and clears storage', async () => {
    localStorage.setItem('access_token', 'test-token')
    useAuthStore.setState({ isAuthenticated: true, username: 'admin' })
    useAuthStore.getState().logout()
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
    expect(useAuthStore.getState().username).toBeNull()
  })
})
