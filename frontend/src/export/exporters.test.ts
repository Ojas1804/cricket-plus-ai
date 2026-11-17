import { expect, test } from 'vitest'
import type { WidgetSpec } from '../types/widget'
import { contextLines, csvEscape, dashboardToJson, exportableRows, safeFilename, widgetToCsv, widgetToJson } from './exporters'

const NOW = new Date('2026-11-17T12:00:00Z')

const spec = (over: Partial<WidgetSpec> = {}): WidgetSpec => ({
  schemaVersion: '1.0', id: 'w1', type: 'leaderboard', title: 'Top IPL Run Scorers', description: 'Career runs', query: {},
  data: { columns: ['rank', 'player', 'runs'], rows: [{ rank: 1, player: 'V Kohli', runs: 8004 }, { rank: 2, player: 'Smith, "Steve"', runs: 5000 }], extra: {} },
  metadata: {
    source: 'internal_analytics', lastUpdated: '2026-11-16T10:00:00Z', isMock: false,
    filters: { competition: 'IPL' }, coverage: { matches: 1000, earliestMatch: '2008-04-18' },
    provenance: { executedAt: '2026-11-16T10:00:00Z', cached: true, lastIngestion: '2026-11-15T09:00:00Z',
      definitions: { batting_average: 'runs / dismissals' }, notes: ['Aggregate filters applied after aggregation.'], warnings: ['2 matches unknown venue country'] },
  },
  interactions: { selectableRows: true, linkedEntity: 'player', subscribesTo: [] },
  ...over,
})

test('csv escaping handles commas, quotes, newlines and formula injection', () => {
  expect(csvEscape('a,b')).toBe('"a,b"')
  expect(csvEscape('say "hi"')).toBe('"say ""hi"""')
  expect(csvEscape('line1\nline2')).toBe('"line1\nline2"')
  expect(csvEscape('=SUM(A1)')).toBe("'=SUM(A1)")
  expect(csvEscape('@cmd')).toBe("'@cmd")
  expect(csvEscape('-5')).toBe('-5')
  expect(csvEscape(-5)).toBe('-5')
  expect(csvEscape(null)).toBe('')
  expect(csvEscape({ a: 1 })).toBe('"{""a"":1}"')
})

test('csv export keeps the full statistical context as comment lines above the data', () => {
  const csv = widgetToCsv(spec(), NOW)!
  const lines = csv.trim().split('\n')
  const header = lines.findIndex((l) => !l.startsWith('# '))
  const preamble = lines.slice(0, header).join('\n')
  expect(preamble).toContain('# Widget: Top IPL Run Scorers')
  expect(preamble).toContain('# Source: internal_analytics')
  expect(preamble).toContain('# Exported at: 2026-11-17T12:00:00.000Z')
  expect(preamble).toContain('# Filters: {"competition":"IPL"}')
  expect(preamble).toContain('# Coverage: {"matches":1000,"earliestMatch":"2008-04-18"}')
  expect(preamble).toContain('# Definition - batting_average: runs / dismissals')
  expect(preamble).toContain('# Warning: 2 matches unknown venue country')
  expect(preamble).toContain('# Served from cache: yes')
  expect(lines[header]).toBe('rank,player,runs')
  expect(lines[header + 1]).toBe('1,V Kohli,8004')
  expect(lines[header + 2]).toBe('2,"Smith, ""Steve""",5000')
})

test('mock data is flagged in exports', () => {
  const s = spec({ metadata: { ...spec().metadata, isMock: true } })
  expect(contextLines(s, NOW).join('\n')).toContain('MOCK DATA')
  expect(widgetToJson(s, NOW)).toContain('MOCK DATA')
})

test('non-tabular widgets have no csv but still export json with context', () => {
  const text = spec({ type: 'text', data: { columns: [], rows: [], extra: { text: 'hi' } } })
  expect(widgetToCsv(text, NOW)).toBeNull()
  const json = JSON.parse(widgetToJson(text, NOW))
  expect(json.widget.id).toBe('w1')
  expect(json.context[0]).toBe('Widget: Top IPL Run Scorers')
  expect(spec({ data: { columns: [], rows: [], extra: {} } })).toBeDefined()
  expect(exportableRows(spec({ data: { columns: [], rows: [], extra: {} } }))).toBeNull()
})

test('profile widgets export their statistics as rows', () => {
  const p = spec({ type: 'player_profile', data: { columns: [], rows: [], extra: { name: 'V Kohli', stats: { runs: 8004, 'batting average': 38.7 } } } })
  const csv = widgetToCsv(p, NOW)!
  expect(csv).toContain('statistic,value')
  expect(csv).toContain('batting average,38.7')
})

test('dashboard export contains every widget with layout and state', () => {
  const widgets = { w1: { spec: spec(), status: 'READY' as const, expanded: true, linked: false, layout: { x: 0, y: 0, w: 6, h: 8 } } }
  const out = JSON.parse(dashboardToJson(widgets, ['w1', 'gone'], NOW))
  expect(out.widgets).toHaveLength(1)
  expect(out.widgets[0].layout).toEqual({ x: 0, y: 0, w: 6, h: 8 })
  expect(out.exportedAt).toBe('2026-11-17T12:00:00.000Z')
})

test('filenames are safe', () => {
  expect(safeFilename('Top IPL: Run/Scorers!')).toBe('top-ipl-run-scorers')
  expect(safeFilename('***')).toBe('widget')
})
