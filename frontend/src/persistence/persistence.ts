import type { StoreApi } from 'zustand'
import { z } from 'zod'
import { useDashboardStore } from '../stores/dashboardStore'
import { useHistoryStore, type HistoryEntry } from '../stores/historyStore'
import { WidgetSpecSchema, type WidgetState } from '../types/widget'
import type { KeyValueStore } from './kvStore'

export const DASHBOARD_KEY = 'dashboard'
export const HISTORY_KEY = 'history'
const VERSION = 1

const LayoutSchema = z.object({ x: z.number(), y: z.number(), w: z.number(), h: z.number() })
const PersistedWidgetSchema = z.object({ spec: WidgetSpecSchema, layout: LayoutSchema, expanded: z.boolean(), linked: z.boolean() })
const PersistedDashboardSchema = z.object({
  version: z.literal(VERSION), savedAt: z.string().optional(), order: z.array(z.string()), widgets: z.record(z.string(), z.unknown()),
})
const HistorySchema = z.array(z.object({
  id: z.string(), prompt: z.string(), action: z.enum(['ADD', 'UPDATE']), targetWidgetId: z.string().nullable(), createdAt: z.string(),
  status: z.enum(['COMPLETED', 'CLARIFICATION_REQUIRED', 'FAILED']), widgetIds: z.array(z.string()),
}))

export interface PersistedDashboard {
  version: typeof VERSION
  savedAt?: string
  order: string[]
  widgets: Record<string, { spec: unknown; layout: WidgetState['layout']; expanded: boolean; linked: boolean }>
}

export function serializeDashboard(widgets: Record<string, WidgetState>, order: string[], now = new Date()): PersistedDashboard {
  return {
    version: VERSION, savedAt: now.toISOString(), order,
    widgets: Object.fromEntries(order.filter((id) => widgets[id]).map((id) => {
      const { spec, layout, expanded, linked } = widgets[id]
      return [id, { spec, layout, expanded, linked }]
    })),
  }
}

export function deserializeDashboard(raw: unknown): { widgets: Record<string, WidgetState>; order: string[] } | null {
  const parsed = PersistedDashboardSchema.safeParse(raw)
  if (!parsed.success) return null
  const widgets: Record<string, WidgetState> = {}
  const order: string[] = []
  for (const id of parsed.data.order) {
    const w = PersistedWidgetSchema.safeParse(parsed.data.widgets[id])
    if (w.success && w.data.spec.id === id) {
      widgets[id] = { ...w.data, status: 'READY' }
      order.push(id)
    }
  }
  return { widgets, order }
}

export function startAutoSave<S>(store: StoreApi<S>, kv: KeyValueStore, key: string, pick: (s: S) => unknown, debounceMs = 400): () => void {
  let last = JSON.stringify(pick(store.getState()))
  let timer: ReturnType<typeof setTimeout> | undefined
  const unsubscribe = store.subscribe((state) => {
    const snapshot = pick(state)
    const json = JSON.stringify(snapshot)
    if (json === last) return
    clearTimeout(timer)
    timer = setTimeout(() => {
      last = json
      kv.set(key, snapshot).catch((e) => console.warn('Could not persist', key, e))
    }, debounceMs)
  })
  return () => { clearTimeout(timer); unsubscribe() }
}

const pickDashboard = (s: { widgets: Record<string, WidgetState>; order: string[] }) => {
  const { savedAt: _ignored, ...rest } = serializeDashboard(s.widgets, s.order)
  return rest
}

export async function hydrateApp(kv: KeyValueStore, attach: (specs: WidgetState['spec'][]) => Promise<unknown>): Promise<() => void> {
  try {
    const restored = deserializeDashboard(await kv.get(DASHBOARD_KEY))
    if (restored?.order.length) {
      useDashboardStore.getState().restore(restored.widgets, restored.order)
      attach(restored.order.map((id) => restored.widgets[id].spec)).catch(() => undefined)
    }
    const history = HistorySchema.safeParse(await kv.get(HISTORY_KEY))
    if (history.success) useHistoryStore.getState().restore(history.data as HistoryEntry[])
  } catch (e) {
    console.warn('Could not restore saved workspace', e)
  }
  useDashboardStore.getState().setHydrated(true)
  const stops = [
    startAutoSave(useDashboardStore, kv, DASHBOARD_KEY, pickDashboard),
    startAutoSave(useHistoryStore, kv, HISTORY_KEY, (s) => s.entries),
  ]
  return () => stops.forEach((s) => s())
}
