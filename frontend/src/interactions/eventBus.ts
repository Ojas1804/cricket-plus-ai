export interface EntityRef { type: 'PLAYER' | 'TEAM' | 'MATCH' | 'COMPETITION' | 'VENUE'; id: string; label?: string }

export interface WidgetEvent {
  event: 'PLAYER_SELECTED' | 'TEAM_SELECTED' | 'MATCH_SELECTED'
  entity: EntityRef
  sourceWidgetId: string
}

type Handler = (e: WidgetEvent) => void

const handlers = new Set<Handler>()

export const eventBus = {
  emit(e: WidgetEvent) {
    handlers.forEach((h) => h(e))
  },
  subscribe(h: Handler) {
    handlers.add(h)
    return () => { handlers.delete(h) }
  },
}
