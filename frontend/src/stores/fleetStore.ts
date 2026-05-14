import { create } from 'zustand'
import type { Bot, BotStatus, BotMode } from '../types'
import { getBots } from '../api/bots'

interface FleetFilters {
  status: string
  mode: string
  platform_id: string
}

interface FleetState {
  bots: Bot[]
  filters: FleetFilters
  selectedBotIds: string[]
  loading: boolean
  fetchBots: () => Promise<void>
  updateBotStatus: (id: string, status: BotStatus) => void
  setBotMode: (id: string, mode: BotMode) => void
  setFilter: (key: keyof FleetFilters, value: string) => void
  toggleSelect: (id: string) => void
  selectAll: () => void
  clearSelection: () => void
}

export const useFleetStore = create<FleetState>((set, get) => ({
  bots: [],
  filters: { status: '', mode: '', platform_id: '' },
  selectedBotIds: [],
  loading: false,

  fetchBots: async () => {
    set({ loading: true })
    try {
      const { filters } = get()
      const params: Record<string, string> = {}
      if (filters.status) params.status = filters.status
      if (filters.mode) params.mode = filters.mode
      if (filters.platform_id) params.platform_id = filters.platform_id
      const bots = await getBots(params)
      set({ bots })
    } finally {
      set({ loading: false })
    }
  },

  updateBotStatus: (id, status) =>
    set((s) => ({ bots: s.bots.map((b) => (b.id === id ? { ...b, status } : b)) })),

  setBotMode: (id, mode) =>
    set((s) => ({ bots: s.bots.map((b) => (b.id === id ? { ...b, mode } : b)) })),

  setFilter: (key, value) => {
    set((s) => ({ filters: { ...s.filters, [key]: value } }))
    get().fetchBots()
  },

  toggleSelect: (id) =>
    set((s) => ({
      selectedBotIds: s.selectedBotIds.includes(id)
        ? s.selectedBotIds.filter((x) => x !== id)
        : [...s.selectedBotIds, id],
    })),

  selectAll: () => set((s) => ({ selectedBotIds: s.bots.map((b) => b.id) })),
  clearSelection: () => set({ selectedBotIds: [] }),
}))
