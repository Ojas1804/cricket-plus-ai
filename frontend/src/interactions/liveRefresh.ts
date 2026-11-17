import { useDashboardStore } from '../stores/dashboardStore'
import type { WidgetSpec } from '../types/widget'

export interface LiveInfo { matchId: string; refreshSeconds: number }

export function liveInfo(spec: WidgetSpec): LiveInfo | null {
  const live = spec.query.live as { matchId?: string; refreshSeconds?: number } | undefined
  return live?.matchId ? { matchId: live.matchId, refreshSeconds: live.refreshSeconds ?? 60 } : null
}

type Fetch = (matchId: string, widgetId: string) => Promise<WidgetSpec>

export async function refreshLive(widgetId: string, fetchWidget: Fetch, silent = true): Promise<void> {
  const store = useDashboardStore.getState()
  const w = store.widgets[widgetId]
  const info = w && liveInfo(w.spec)
  if (!info) return
  if (!silent) store.setStatus(widgetId, 'REFRESHING')
  try {
    store.replaceSpec(widgetId, await fetchWidget(info.matchId, widgetId))
  } catch (e) {
    store.setStatus(widgetId, 'ERROR', e instanceof Error ? e.message : 'Live update failed')
  }
}
