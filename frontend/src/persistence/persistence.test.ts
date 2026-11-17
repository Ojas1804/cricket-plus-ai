import 'fake-indexeddb/auto'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { useDashboardStore } from '../stores/dashboardStore'
import { useHistoryStore } from '../stores/historyStore'
import type { WidgetSpec } from '../types/widget'
import { createIdbStore, createMemoryStore } from './kvStore'
import { DASHBOARD_KEY, HISTORY_KEY, deserializeDashboard, hydrateApp, serializeDashboard, startAutoSave } from './persistence'

const spec = (id: string, type = 'leaderboard'): WidgetSpec => ({
  schemaVersion: '1.0', id, type, title: id, description: '', query: {},
  data: { columns: ['a'], rows: [{ a: 1 }], extra: {} },
  metadata: { source: 'internal_analytics', lastUpdated: '2026-11-16T10:00:00Z', filters: {}, coverage: {}, isMock: false, provenance: { warnings: ['w'] } },
  interactions: { selectableRows: true, linkedEntity: 'player', subscribesTo: [] },
})

const reset = () => {
  useDashboardStore.setState({ widgets: {}, order: [], updateTargetId: null, hydrated: false })
  useHistoryStore.setState({ entries: [] })
}
beforeEach(reset)
afterEach(() => { vi.useRealTimers(); reset() })

function seedDashboard() {
  const s = useDashboardStore.getState()
  s.addWidgets([spec('a'), spec('b', 'chart')])
  s.setLayout([{ i: 'a', x: 2, y: 4, w: 5, h: 6 }])
  s.toggleExpanded('b')
  s.toggleLinked('b')
  s.setStatus('a', 'ERROR', 'boom')
}

test('idb store round-trips structured data and deletes', async () => {
  const kv = createIdbStore('test-db-1')
  expect(await kv.get('k')).toBeUndefined()
  await kv.set('k', { a: [1, 2], b: 'x' })
  expect(await kv.get('k')).toEqual({ a: [1, 2], b: 'x' })
  await kv.delete('k')
  expect(await kv.get('k')).toBeUndefined()
})

test('dashboard survives a save/restore cycle with layout and widget state, but not transient status', () => {
  seedDashboard()
  const { widgets, order } = useDashboardStore.getState()
  const restored = deserializeDashboard(JSON.parse(JSON.stringify(serializeDashboard(widgets, order))))!
  expect(restored.order).toEqual(['a', 'b'])
  expect(restored.widgets.a.layout).toEqual({ x: 2, y: 4, w: 5, h: 6 })
  expect(restored.widgets.b.expanded).toBe(false)
  expect(restored.widgets.b.linked).toBe(true)
  expect(restored.widgets.a.status).toBe('READY')
  expect(restored.widgets.a.error).toBeUndefined()
  expect(restored.widgets.a.spec.metadata.provenance).toEqual({ warnings: ['w'] })
})

test('corrupt, outdated and partially invalid data is rejected safely', () => {
  expect(deserializeDashboard(null)).toBeNull()
  expect(deserializeDashboard('junk')).toBeNull()
  expect(deserializeDashboard({ version: 99, order: [], widgets: {} })).toBeNull()
  seedDashboard()
  const { widgets, order } = useDashboardStore.getState()
  const raw = JSON.parse(JSON.stringify(serializeDashboard(widgets, order)))
  raw.widgets.a.spec.type = 5
  raw.widgets.b.spec.id = 'other'
  raw.order.push('ghost')
  expect(deserializeDashboard(raw)).toEqual({ widgets: {}, order: [] })
  delete raw.widgets.a.spec.type
  raw.widgets.a.spec = JSON.parse(JSON.stringify(spec('a')))
  expect(deserializeDashboard(raw)!.order).toEqual(['a'])
})

test('autosave debounces bursts into one write and ignores transient status changes', async () => {
  vi.useFakeTimers()
  const kv = createMemoryStore()
  const stop = startAutoSave(useDashboardStore, kv, DASHBOARD_KEY, (s) => serializeDashboard(s.widgets, s.order, new Date(0)), 400)
  const s = useDashboardStore.getState()
  s.addWidgets([spec('a')])
  s.setLayout([{ i: 'a', x: 1, y: 1, w: 4, h: 4 }])
  s.toggleExpanded('a')
  await vi.advanceTimersByTimeAsync(399)
  expect(kv.writes).toBe(0)
  await vi.advanceTimersByTimeAsync(2)
  expect(kv.writes).toBe(1)
  s.setStatus('a', 'REFRESHING')
  await vi.advanceTimersByTimeAsync(1000)
  expect(kv.writes).toBe(1)
  stop()
})

test('hydration restores dashboard and history, re-attaches widgets, and never overwrites saved data with empty state', async () => {
  seedDashboard()
  const { widgets, order } = useDashboardStore.getState()
  const saved = serializeDashboard(widgets, order)
  reset()
  const history = [{ id: 'h1', prompt: 'top scorers', action: 'ADD', targetWidgetId: null, createdAt: '2026-11-16T10:00:00Z', status: 'COMPLETED', widgetIds: ['a'] }]
  const kv = createMemoryStore({ [DASHBOARD_KEY]: JSON.parse(JSON.stringify(saved)), [HISTORY_KEY]: history })
  const attached: string[][] = []
  const stop = await hydrateApp(kv, async (specs) => { attached.push(specs.map((x) => x.id)) })
  const state = useDashboardStore.getState()
  expect(state.hydrated).toBe(true)
  expect(state.order).toEqual(['a', 'b'])
  expect(state.widgets.a.layout.x).toBe(2)
  expect(useHistoryStore.getState().entries[0].prompt).toBe('top scorers')
  expect(attached).toEqual([['a', 'b']])
  expect(kv.writes).toBe(0)
  stop()
})

test('hydration with nothing saved or unreadable storage still completes', async () => {
  const stop = await hydrateApp(createMemoryStore(), async () => undefined)
  expect(useDashboardStore.getState().hydrated).toBe(true)
  stop()
  reset()
  const broken = { get: async () => { throw new Error('idb down') }, set: async () => undefined, delete: async () => undefined }
  const stop2 = await hydrateApp(broken, async () => undefined)
  expect(useDashboardStore.getState().hydrated).toBe(true)
  stop2()
})

test('history keeps the newest 50 entries', () => {
  const h = useHistoryStore.getState()
  for (let i = 0; i < 60; i++) h.add({ prompt: `p${i}`, action: 'ADD', targetWidgetId: null, status: 'COMPLETED', widgetIds: [] })
  const { entries } = useHistoryStore.getState()
  expect(entries).toHaveLength(50)
  expect(entries[0].prompt).toBe('p59')
})
