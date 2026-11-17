import { beforeEach, expect, test } from 'vitest'
import type { WidgetSpec } from '../types/widget'
import { useDashboardStore } from './dashboardStore'

const spec = (id: string, type = 'leaderboard'): WidgetSpec => ({
  schemaVersion: '1.0', id, type, title: id, description: '', query: {},
  data: { columns: [], rows: [], extra: {} },
  metadata: { source: 'mock', lastUpdated: '2026-11-16T10:00:00Z', filters: {}, coverage: {}, isMock: true, provenance: {} },
  interactions: { selectableRows: false, linkedEntity: null, subscribesTo: [] },
})

beforeEach(() => useDashboardStore.setState({ widgets: {}, order: [], updateTargetId: null }))

test('widgets coexist and do not overlap', () => {
  useDashboardStore.getState().addWidgets([spec('a'), spec('b')])
  const { widgets } = useDashboardStore.getState()
  expect(widgets.b.layout.y).toBeGreaterThanOrEqual(widgets.a.layout.y + widgets.a.layout.h)
})

test('update preserves id, position and expanded state', () => {
  const s = useDashboardStore.getState()
  s.addWidgets([spec('a')])
  s.setLayout([{ i: 'a', x: 3, y: 5, w: 4, h: 6 }])
  s.toggleExpanded('a')
  s.replaceSpec('a', { ...spec('zzz'), title: 'updated' })
  const w = useDashboardStore.getState().widgets.a
  expect(w.spec.id).toBe('a')
  expect(w.spec.title).toBe('updated')
  expect(w.layout).toEqual({ x: 3, y: 5, w: 4, h: 6 })
  expect(w.expanded).toBe(false)
})

test('removing one widget leaves others untouched', () => {
  const s = useDashboardStore.getState()
  s.addWidgets([spec('a'), spec('b')])
  s.removeWidget('a')
  expect(useDashboardStore.getState().order).toEqual(['b'])
})
