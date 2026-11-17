import { useState } from 'react'
import { DataTable } from '../../components/common/DataTable'
import type { InningsScore, LiveMatchData } from '../../types/live'
import type { WidgetComponentProps } from '../types'

const tokenClass = (t: string) => (t === 'W' ? 'text-red-400' : t === '4' || t === '6' ? 'text-emerald-400' : t === 'Wd' ? 'text-amber-300' : 'text-slate-300')

function Badge({ children, className }: { children: string; className: string }) {
  return <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${className}`}>{children}</span>
}

function InningsDetail({ inn }: { inn: InningsScore }) {
  const batting = inn.batting.map((b) => ({
    batter: b.on_strike ? `${b.player} *` : b.player, status: b.dismissal ?? '', runs: b.runs, balls: b.balls,
    fours: b.fours, sixes: b.sixes, sr: b.strike_rate ?? '-',
  }))
  const bowling = inn.bowling.map((b) => ({ bowler: b.player, overs: b.overs, maidens: b.maidens, runs: b.runs, wickets: b.wickets, econ: b.economy ?? '-' }))
  return (
    <div className="space-y-2 pb-2">
      <DataTable columns={['batter', 'status', 'runs', 'balls', 'fours', 'sixes', 'sr']} rows={batting} />
      <DataTable columns={['bowler', 'overs', 'maidens', 'runs', 'wickets', 'econ']} rows={bowling} />
      {inn.fall_of_wickets.length > 0 && <p className="px-3 text-xs text-slate-400">Fall of wickets: {inn.fall_of_wickets.join(', ')}</p>}
      {inn.did_not_bat.length > 0 && <p className="px-3 text-xs text-slate-400">Did not bat: {inn.did_not_bat.join(', ')}</p>}
    </div>
  )
}

export function ScorecardWidget({ spec, expanded }: WidgetComponentProps) {
  const m = spec.data.extra as unknown as LiveMatchData
  const stale = Boolean(spec.metadata.provenance.stale)
  const [open, setOpen] = useState<Set<number>>(() => new Set(m.current_innings ? [m.current_innings] : []))
  const toggle = (n: number) => setOpen((prev) => {
    const next = new Set(prev)
    if (next.delete(n)) return next
    return next.add(n)
  })

  return (
    <div className="p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        {m.status === 'LIVE' && !stale && <Badge className="bg-red-600">LIVE</Badge>}
        {stale && <Badge className="bg-amber-600">STALE</Badge>}
        {m.status === 'COMPLETED' && <Badge className="bg-slate-600">COMPLETED</Badge>}
        {spec.metadata.isMock && <Badge className="bg-slate-700 text-slate-300">MOCK</Badge>}
        <span className="font-semibold">{m.status_text}</span>
      </div>

      <ul className="mt-2 space-y-0.5">
        {m.innings.map((i) => (
          <li key={i.number} className={i.number === m.current_innings && m.status === 'LIVE' ? 'font-semibold' : 'text-slate-300'}>
            {i.team} {i.runs}/{i.wickets} <span className="text-slate-400">({i.overs} ov)</span>
          </li>
        ))}
      </ul>

      <p className="mt-2 flex flex-wrap gap-x-4 text-xs text-slate-400">
        {m.current_run_rate != null && <span>CRR {m.current_run_rate}</span>}
        {m.required_run_rate != null && <span>RRR {m.required_run_rate}</span>}
        {m.target != null && <span>Target {m.target}</span>}
        {m.partnership && <span>Partnership {m.partnership.runs} ({m.partnership.balls}) {m.partnership.batters.join(' & ')}</span>}
      </p>

      {m.recent_overs.length > 0 && (
        <div className="mt-2 space-y-0.5 text-xs">
          {m.recent_overs.map((o) => (
            <div key={o.over} className="flex gap-2">
              <span className="w-12 text-slate-500">Ov {o.over}</span>
              <span className="flex gap-1.5">{o.balls.map((t, idx) => <span key={idx} className={tokenClass(t)}>{t}</span>)}</span>
              <span className="text-slate-500">= {o.runs}</span>
            </div>
          ))}
        </div>
      )}

      {expanded && (
        <div className="mt-3 divide-y divide-slate-800 border-t border-slate-800">
          {m.innings.map((i) => (
            <div key={i.number}>
              <button className="flex w-full items-center justify-between py-2 text-left text-xs uppercase text-slate-400" onClick={() => toggle(i.number)}>
                <span>{i.team} innings {i.number}</span>
                <span>{open.has(i.number) ? 'Hide' : 'Show'}</span>
              </button>
              {open.has(i.number) && <InningsDetail inn={i} />}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
