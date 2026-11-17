import { ChevronDown, ChevronRight, GripVertical, MoreVertical, RefreshCw } from 'lucide-react'
import { memo, useEffect, useRef, useState } from 'react'
import { download, safeFilename, widgetToCsv, widgetToJson } from '../export/exporters'
import { isLinkable } from '../interactions/linking'
import { liveInfo, refreshLive } from '../interactions/liveRefresh'
import { fetchLiveWidget, refreshWidget, registerWidget, removeWidget } from '../services/api'
import { AUTO_HEIGHT_TYPES, useDashboardStore } from '../stores/dashboardStore'
import type { WidgetState } from '../types/widget'
import { WidgetRenderer } from '../widgets/renderer'

export const ROW_HEIGHT = 30
export const MARGIN = 12
const HEADER_PX = 44

export const WidgetFrame = memo(function WidgetFrame({ state }: { state: WidgetState }) {
  const { spec, status, error, expanded } = state
  const store = useDashboardStore.getState()
  const [menu, setMenu] = useState(false)
  const bodyRef = useRef<HTMLDivElement>(null)
  const auto = AUTO_HEIGHT_TYPES.has(spec.type)
  const warnings = (spec.metadata.provenance.warnings ?? []) as string[]

  useEffect(() => {
    if (!auto || !expanded || !bodyRef.current) return
    const el = bodyRef.current
    const fit = () => {
      const h = Math.max(2, Math.ceil((el.scrollHeight + HEADER_PX + MARGIN) / (ROW_HEIGHT + MARGIN)))
      const cur = useDashboardStore.getState().widgets[spec.id]
      if (cur && cur.layout.h !== h) store.setLayout([{ i: spec.id, ...cur.layout, h }])
    }
    fit()
    const ro = new ResizeObserver(fit)
    ro.observe(el)
    return () => ro.disconnect()
  }, [auto, expanded, spec, store])

  const live = liveInfo(spec)
  const liveSeconds = live?.refreshSeconds
  useEffect(() => {
    if (!liveSeconds) return
    const tick = () => { if (document.visibilityState === 'visible') void refreshLive(spec.id, fetchLiveWidget) }
    const timer = setInterval(tick, liveSeconds * 1000)
    return () => clearInterval(timer)
  }, [liveSeconds, spec.id])

  const refresh = async () => {
    if (live) return refreshLive(spec.id, fetchLiveWidget, false)
    store.setStatus(spec.id, 'REFRESHING')
    try {
      store.replaceSpec(spec.id, await refreshWidget(spec.id))
    } catch (e) {
      store.setStatus(spec.id, 'ERROR', e instanceof Error ? e.message : 'Refresh failed')
    }
  }

  const duplicate = async () => {
    const copy = { ...spec, id: `widget-${crypto.randomUUID().slice(0, 8)}`, title: `${spec.title} (copy)` }
    try {
      await registerWidget(copy)
      store.addWidgets([copy])
    } catch (e) {
      store.setStatus(spec.id, 'ERROR', e instanceof Error ? e.message : 'Duplicate failed')
    }
  }

  const remove = async () => {
    store.removeWidget(spec.id)
    await removeWidget(spec.id).catch(() => undefined)
  }

  const exportJson = () => download(`${safeFilename(spec.title)}.json`, 'application/json', widgetToJson(spec))
  const csv = widgetToCsv(spec)
  const exportCsv = () => csv && download(`${safeFilename(spec.title)}.csv`, 'text/csv', csv)

  const item = (label: string, fn: () => void) => (
    <button key={label} className="block w-full px-3 py-1.5 text-left text-sm hover:bg-slate-700"
      onClick={() => { setMenu(false); fn() }}>{label}</button>
  )

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900 shadow-lg">
      <header className="flex items-center gap-2 border-b border-slate-800 px-2" style={{ height: HEADER_PX }}>
        <span className="widget-drag-handle cursor-grab text-slate-500" title="Drag"><GripVertical size={16} /></span>
        <button onClick={() => store.toggleExpanded(spec.id)} aria-label="Expand or collapse">
          {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        </button>
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-sm font-semibold">{spec.title}</h2>
          <p className="truncate text-[11px] text-slate-500">
            {spec.metadata.source}{spec.metadata.isMock ? ' (mock)' : ''} · {new Date(spec.metadata.lastUpdated).toLocaleTimeString()}
            {state.linked && ' · linked'}{status !== 'READY' && ` · ${status}`}
          </p>
        </div>
        <button onClick={refresh} aria-label="Refresh" className={status === 'REFRESHING' ? 'animate-spin' : ''}>
          <RefreshCw size={14} />
        </button>
        <div className="relative">
          <button onClick={() => setMenu((m) => !m)} aria-label="Menu"><MoreVertical size={16} /></button>
          {menu && (
            <div className="absolute right-0 z-20 w-36 rounded border border-slate-700 bg-slate-800 py-1 shadow-xl">
              {item('Edit query', () => store.setUpdateTarget(spec.id))}
              {item('Update widget', () => store.setUpdateTarget(spec.id))}
              {isLinkable(spec) && item(state.linked ? 'Unlink from selection' : 'Link to selection', () => store.toggleLinked(spec.id))}
              {item('Duplicate', duplicate)}
              {item('Refresh', refresh)}
              {item('Export JSON', exportJson)}
              {csv && item('Export CSV', exportCsv)}
              {item('Remove', remove)}
            </div>
          )}
        </div>
      </header>
      {expanded && (
        <div ref={bodyRef} className="min-h-0 flex-1 overflow-auto">
          {status === 'ERROR' && (
            <div className="m-2 rounded border border-red-800 bg-red-950 p-2 text-sm">
              <p className="text-red-300">Failed: {error}</p>
              <p className="text-xs text-slate-400">Showing stale data. Last successful update: {new Date(spec.metadata.lastUpdated).toLocaleString()}</p>
              <button className="mt-1 rounded bg-slate-700 px-2 py-0.5 text-xs" onClick={refresh}>Retry</button>
            </div>
          )}
          <WidgetRenderer spec={spec} expanded={expanded} />
          {warnings.length > 0 && (
            <ul className="m-2 space-y-1 rounded bg-amber-900/30 p-2 text-xs text-amber-200">
              {warnings.map((w) => <li key={w}>{w}</li>)}
            </ul>
          )}
        </div>
      )}
    </div>
  )
})
