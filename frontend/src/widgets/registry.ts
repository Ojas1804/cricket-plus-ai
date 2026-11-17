import { lazy, type ComponentType, type LazyExoticComponent } from 'react'
import { ComparisonWidget } from './comparison/ComparisonWidget'
import { LeaderboardWidget } from './leaderboard/LeaderboardWidget'
import { PlayerProfileWidget } from './profile/PlayerProfileWidget'
import { ScorecardWidget } from './scorecard/ScorecardWidget'
import { TableWidget } from './table/TableWidget'
import { TextWidget } from './text/TextWidget'
import type { WidgetComponentProps } from './types'

const ChartWidget = lazy(() => import('./chart/ChartWidget').then((m) => ({ default: m.ChartWidget })))

export const widgetRegistry: Record<string, ComponentType<WidgetComponentProps> | LazyExoticComponent<ComponentType<WidgetComponentProps>>> = {
  scorecard: ScorecardWidget,
  leaderboard: LeaderboardWidget,
  table: TableWidget,
  chart: ChartWidget,
  player_profile: PlayerProfileWidget,
  comparison: ComparisonWidget,
  text: TextWidget,
}
