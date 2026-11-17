import { beforeEach, expect, test } from 'vitest'
import { useDashboardStore } from '../stores/dashboardStore'
import type { WidgetSpec } from '../types/widget'
import { liveInfo, refreshLive } from './liveRefresh'

const spec = (id: string, title = id, live = true): WidgetSpec => ({
  schemaVersion: '1.0', id, type: 'scorecard', title, description: '',
  query: live ? { live: { matchId: `m-${id}`, refreshSeconds: 30 } } : {},
  data: { columns: [], rows: [], extra: {} },
  metadata: { source: 'live:mock', lastUpdated: '2026-11-16T10:00:00Z', filters: {}, coverage: {}, isMock: true, provenance: {} },
  interactions: { selectableRows: false, linkedEntity: null, subscribesTo: [] },
})

beforeEach(() => {
  useDashboardStore.setState({ widgets: {}, order: [], updateTargetId: null })
  useDashboardStore.getState().addWidgets([spec('a'), spec('b'), spec('plain', 'plain', false)])
})

test('liveInfo reads the match id and cadence', () => {
  expect(liveInfo(spec('a'))).toEqual({ matchId: 'm-a', refreshSeconds: 30 })
  expect(liveInfo(spec('x', 'x', false))).toBeNull()
})

test('a live update keeps position, size and collapsed state and leaves other widgets alone', async () => {
  const s = useDashboardStore.getState()
  s.setLayout([{ i: 'a', x: 2, y: 3, w: 5, h: 7 }])
  s.toggleExpanded('a')
  await refreshLive('a', async (matchId, id) => spec(id, `updated ${matchId}`))
  const w = useDashboardStore.getState().widgets
  expect(w.a.spec.title).toBe('updated m-a')
  expect(w.a.layout).toEqual({ x: 2, y: 3, w: 5, h: 7 })
  expect(w.a.expanded).toBe(false)
  expect(w.a.status).toBe('READY')
  expect(w.b.spec.title).toBe('b')
})

test('a failed poll marks only that widget as errored, keeps the last known data, and recovers', async () => {
  await refreshLive('a', async () => { throw new Error('provider down') })
  let w = useDashboardStore.getState().widgets
  expect(w.a.status).toBe('ERROR')
  expect(w.a.error).toBe('provider down')
  expect(w.a.spec.title).toBe('a')
  expect(w.b.status).toBe('READY')
  await refreshLive('a', async (_m, id) => spec(id, 'recovered'))
  w = useDashboardStore.getState().widgets
  expect(w.a.status).toBe('READY')
  expect(w.a.error).toBeUndefined()
  expect(w.a.spec.title).toBe('recovered')
})

test('non-live widgets are ignored', async () => {
  let called = false
  await refreshLive('plain', async (_m, id) => { called = true; return spec(id) })
  expect(called).toBe(false)
})
