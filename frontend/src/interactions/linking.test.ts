import { afterEach, beforeEach, expect, test } from 'vitest'
import { useDashboardStore } from '../stores/dashboardStore'
import type { WidgetSpec } from '../types/widget'
import { eventBus } from './eventBus'
import { startLinking } from './linking'

const spec = (id: string, type: string, dsl = true, subscribes = false): WidgetSpec => ({
  schemaVersion: '1.0', id, type, title: id, description: '', query: dsl ? { dsl: { entity: 'player' } } : {},
  data: { columns: [], rows: [], extra: {} },
  metadata: { source: 'internal_analytics', lastUpdated: '2026-11-16T10:00:00Z', filters: {}, coverage: {}, isMock: false, provenance: {} },
  interactions: { selectableRows: false, linkedEntity: null, subscribesTo: subscribes ? ['PLAYER_SELECTED'] : [] },
})

let stop: () => void
const tick = () => new Promise((r) => setTimeout(r, 0))
const select = (source: string, id = '7') =>
  eventBus.emit({ event: 'PLAYER_SELECTED', entity: { type: 'PLAYER', id }, sourceWidgetId: source })

beforeEach(() => {
  useDashboardStore.setState({ widgets: {}, order: [], updateTargetId: null })
  useDashboardStore.getState().addWidgets([
    spec('src', 'leaderboard'), spec('profile', 'player_profile', true, true), spec('chart', 'chart'), spec('mock', 'table', false, true),
  ])
})
afterEach(() => stop())

test('only linked, linkable widgets update and others stay untouched', async () => {
  const calls: [string, number][] = []
  stop = startLinking(async (id, pid) => { calls.push([id, pid]); return { ...spec(id, 'player_profile'), title: `p${pid}` } })
  select('src')
  await tick()
  expect(calls).toEqual([['profile', 7]])
  const w = useDashboardStore.getState().widgets
  expect(w.profile.spec.title).toBe('p7')
  expect(w.chart.spec.title).toBe('chart')
  expect(w.profile.layout).toBeDefined()
})

test('toggling link subscribes a widget and failures stay isolated', async () => {
  useDashboardStore.getState().toggleLinked('chart')
  stop = startLinking(async (id) => { if (id === 'chart') throw new Error('boom'); return spec(id, 'player_profile') })
  select('src')
  await tick()
  const w = useDashboardStore.getState().widgets
  expect(w.chart.status).toBe('ERROR')
  expect(w.profile.status).toBe('READY')
})

test('source widget never updates itself', async () => {
  const calls: string[] = []
  stop = startLinking(async (id) => { calls.push(id); return spec(id, 'player_profile') })
  select('profile')
  await tick()
  expect(calls).toEqual([])
})
