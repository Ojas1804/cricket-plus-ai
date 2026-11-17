import type { WidgetSpec, WidgetState } from '../types/widget'

const TABULAR_TYPES = new Set(['table', 'leaderboard', 'comparison', 'chart', 'player_profile'])

export function csvEscape(value: unknown): string {
  if (value == null) return ''
  let s = typeof value === 'object' ? JSON.stringify(value) : String(value)
  if (typeof value === 'string' && /^[=+\-@\t\r]/.test(s) && Number.isNaN(Number(s))) s = `'${s}`
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

const oneLine = (s: unknown) => String(s).replace(/[\r\n]+/g, ' ')

export function exportableRows(spec: WidgetSpec): { columns: string[]; rows: Record<string, unknown>[] } | null {
  if (!TABULAR_TYPES.has(spec.type)) return null
  let { columns, rows } = spec.data
  if (spec.type === 'player_profile') {
    const stats = (spec.data.extra.stats ?? {}) as Record<string, unknown>
    columns = ['statistic', 'value']
    rows = Object.entries(stats).map(([statistic, value]) => ({ statistic, value }))
  }
  if (!rows.length) return null
  return { columns: columns.length ? columns : Object.keys(rows[0]), rows }
}

export function contextLines(spec: WidgetSpec, now: Date): string[] {
  const m = spec.metadata
  const p = m.provenance as Record<string, unknown>
  const lines = [
    `Widget: ${spec.title}`,
    spec.description && `Description: ${spec.description}`,
    `Source: ${m.source}${m.isMock ? ' (MOCK DATA, not real cricket statistics)' : ''}`,
    `Data last updated: ${m.lastUpdated}`,
    p.executedAt && `Query executed: ${p.executedAt}`,
    p.cached && 'Served from cache: yes',
    p.lastIngestion && `Last data ingestion: ${p.lastIngestion}`,
    `Exported at: ${now.toISOString()}`,
    Object.keys(m.filters).length > 0 && `Filters: ${JSON.stringify(m.filters)}`,
    Object.keys(m.coverage).length > 0 && `Coverage: ${JSON.stringify(m.coverage)}`,
  ]
  for (const [name, text] of Object.entries((p.definitions ?? {}) as Record<string, string>)) lines.push(`Definition - ${name}: ${text}`)
  for (const n of (p.notes ?? []) as string[]) lines.push(`Note: ${n}`)
  for (const w of (p.warnings ?? []) as string[]) lines.push(`Warning: ${w}`)
  return lines.filter((l): l is string => Boolean(l))
}

export function widgetToCsv(spec: WidgetSpec, now = new Date()): string | null {
  const data = exportableRows(spec)
  if (!data) return null
  const preamble = contextLines(spec, now).map((l) => `# ${oneLine(l)}`)
  const body = [data.columns.map(csvEscape).join(','), ...data.rows.map((r) => data.columns.map((c) => csvEscape(r[c])).join(','))]
  return [...preamble, ...body].join('\n') + '\n'
}

export function widgetToJson(spec: WidgetSpec, now = new Date()): string {
  return JSON.stringify({ exportedAt: now.toISOString(), context: contextLines(spec, now), widget: spec }, null, 2)
}

export function dashboardToJson(widgets: Record<string, WidgetState>, order: string[], now = new Date()): string {
  return JSON.stringify({
    exportedAt: now.toISOString(), version: 1,
    widgets: order.filter((id) => widgets[id]).map((id) => {
      const { spec, layout, expanded, linked } = widgets[id]
      return { spec, layout, expanded, linked }
    }),
  }, null, 2)
}

export function download(filename: string, mime: string, content: string): void {
  const url = URL.createObjectURL(new Blob([content], { type: `${mime};charset=utf-8` }))
  const a = Object.assign(document.createElement('a'), { href: url, download: filename })
  a.click()
  URL.revokeObjectURL(url)
}

export const safeFilename = (s: string) => s.replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '').toLowerCase() || 'widget'
