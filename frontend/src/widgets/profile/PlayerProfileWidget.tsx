import type { WidgetComponentProps } from '../types'

export function PlayerProfileWidget({ spec }: WidgetComponentProps) {
  const stats = (spec.data.extra.stats ?? {}) as Record<string, unknown>
  return (
    <div className="p-3 text-sm">
      <h3 className="mb-2 text-lg font-semibold">{String(spec.data.extra.name ?? spec.title)}</h3>
      <dl className="grid grid-cols-2 gap-2">
        {Object.entries(stats).map(([k, v]) => (
          <div key={k} className="rounded bg-slate-800 p-2">
            <dt className="text-xs uppercase text-slate-400">{k}</dt>
            <dd className="font-medium">{v == null ? 'n/a' : String(v)}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
