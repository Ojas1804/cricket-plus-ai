import { create } from 'zustand'
import type { PromptAction } from '../types/widget'

export const MAX_HISTORY = 50

export interface HistoryEntry {
  id: string
  prompt: string
  action: PromptAction
  targetWidgetId: string | null
  createdAt: string
  status: 'COMPLETED' | 'CLARIFICATION_REQUIRED' | 'FAILED'
  widgetIds: string[]
}

interface HistoryState {
  entries: HistoryEntry[]
  add: (entry: Omit<HistoryEntry, 'id' | 'createdAt'>) => void
  restore: (entries: HistoryEntry[]) => void
  clear: () => void
}

export const useHistoryStore = create<HistoryState>((set) => ({
  entries: [],
  add: (entry) => set((s) => ({
    entries: [{ ...entry, id: crypto.randomUUID(), createdAt: new Date().toISOString() }, ...s.entries].slice(0, MAX_HISTORY),
  })),
  restore: (entries) => set({ entries: entries.slice(0, MAX_HISTORY) }),
  clear: () => set({ entries: [] }),
}))
