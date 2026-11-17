import { create } from 'zustand'
import type { GridPosition, WidgetSpec, WidgetState, WidgetStatus } from '../types/widget'

const COLS = 12
const DEFAULT_SIZE: Record<string, { w: number; h: number }> = {
  text: { w: 4, h: 4 }, scorecard: { w: 6, h: 9 }, chart: { w: 6, h: 9 }, comparison: { w: 6, h: 8 },
  player_profile: { w: 4, h: 9 }, leaderboard: { w: 6, h: 10 }, table: { w: 6, h: 10 },
}

export const AUTO_HEIGHT_TYPES = new Set(['text'])
export const RESIZABLE_TYPES = new Set(['table', 'leaderboard', 'chart', 'scorecard', 'image', 'comparison', 'player_profile'])

interface DashboardState {
  widgets: Record<string, WidgetState>
  order: string[]
  updateTargetId: string | null
  hydrated: boolean
  restore: (widgets: Record<string, WidgetState>, order: string[]) => void
  setHydrated: (v: boolean) => void
  addWidgets: (specs: WidgetSpec[]) => void
  replaceSpec: (id: string, spec: WidgetSpec) => void
  setStatus: (id: string, status: WidgetStatus, error?: string) => void
  removeWidget: (id: string) => void
  toggleExpanded: (id: string) => void
  toggleLinked: (id: string) => void
  setLayout: (items: { i: string; x: number; y: number; w: number; h: number }[]) => void
  setUpdateTarget: (id: string | null) => void
}

function nextPosition(widgets: Record<string, WidgetState>, w: number, h: number): GridPosition {
  const bottom = Object.values(widgets).reduce((m, s) => Math.max(m, s.layout.y + s.layout.h), 0)
  return { x: 0, y: bottom, w, h }
}

export const useDashboardStore = create<DashboardState>((set) => ({
  widgets: {},
  order: [],
  updateTargetId: null,
  hydrated: false,
  restore: (widgets, order) => set({ widgets, order }),
  setHydrated: (hydrated) => set({ hydrated }),

  addWidgets: (specs) => set((s) => {
    const widgets = { ...s.widgets }
    const order = [...s.order]
    for (const spec of specs) {
      if (widgets[spec.id]) continue
      const size = DEFAULT_SIZE[spec.type] ?? { w: 6, h: 8 }
      widgets[spec.id] = { spec, status: 'READY', expanded: true, linked: spec.interactions.subscribesTo.includes('PLAYER_SELECTED'), layout: nextPosition(widgets, Math.min(size.w, COLS), size.h) }
      order.push(spec.id)
    }
    return { widgets, order }
  }),

  replaceSpec: (id, spec) => set((s) => s.widgets[id]
    ? { widgets: { ...s.widgets, [id]: { ...s.widgets[id], spec: { ...spec, id }, status: 'READY', error: undefined } } }
    : s),

  setStatus: (id, status, error) => set((s) => s.widgets[id]
    ? { widgets: { ...s.widgets, [id]: { ...s.widgets[id], status, error } } }
    : s),

  removeWidget: (id) => set((s) => {
    const { [id]: _removed, ...widgets } = s.widgets
    return { widgets, order: s.order.filter((o) => o !== id), updateTargetId: s.updateTargetId === id ? null : s.updateTargetId }
  }),

  toggleExpanded: (id) => set((s) => s.widgets[id]
    ? { widgets: { ...s.widgets, [id]: { ...s.widgets[id], expanded: !s.widgets[id].expanded } } }
    : s),

  toggleLinked: (id) => set((s) => s.widgets[id]
    ? { widgets: { ...s.widgets, [id]: { ...s.widgets[id], linked: !s.widgets[id].linked } } }
    : s),

  setLayout: (items) => set((s) => {
    const widgets = { ...s.widgets }
    for (const { i, x, y, w, h } of items) {
      const cur = widgets[i]
      if (cur && (cur.layout.x !== x || cur.layout.y !== y || cur.layout.w !== w || cur.layout.h !== h)) {
        widgets[i] = { ...cur, layout: { x, y, w, h } }
      }
    }
    return { widgets }
  }),

  setUpdateTarget: (id) => set({ updateTargetId: id }),
}))
