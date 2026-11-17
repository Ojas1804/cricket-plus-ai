import { useDashboardStore } from '../stores/dashboardStore'
import type { WidgetSpec } from '../types/widget'
import { eventBus } from './eventBus'

export const LINKABLE_TYPES = new Set(['player_profile', 'chart', 'table'])

export function isLinkable(spec: WidgetSpec): boolean {
  const dsl = spec.query.dsl as { entity?: string } | undefined
  return LINKABLE_TYPES.has(spec.type) && ('profile' in spec.query || dsl?.entity === 'player')
}

type Focus = (widgetId: string, playerId: number) => Promise<WidgetSpec>

export function startLinking(focus: Focus): () => void {
  return eventBus.subscribe(async (e) => {
    if (e.event !== 'PLAYER_SELECTED') return
    const playerId = Number(e.entity.id)
    if (!Number.isInteger(playerId)) return
    const store = useDashboardStore.getState()
    const targets = Object.values(store.widgets).filter((w) => w.linked && w.spec.id !== e.sourceWidgetId && isLinkable(w.spec))
    await Promise.all(targets.map(async ({ spec }) => {
      store.setStatus(spec.id, 'REFRESHING')
      try {
        store.replaceSpec(spec.id, await focus(spec.id, playerId))
      } catch (err) {
        store.setStatus(spec.id, 'ERROR', err instanceof Error ? err.message : 'Update failed')
      }
    }))
  })
}
