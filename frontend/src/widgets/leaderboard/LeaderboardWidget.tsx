import { useState } from 'react'
import { DataTable } from '../../components/common/DataTable'
import { eventBus } from '../../interactions/eventBus'
import { createProfileWidget } from '../../services/api'
import { useDashboardStore } from '../../stores/dashboardStore'
import type { WidgetComponentProps } from '../types'

export function LeaderboardWidget({ spec }: WidgetComponentProps) {
  const [selected, setSelected] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const selectable = spec.interactions.selectableRows
  const row = selected != null ? spec.data.rows[selected] : null
  const playerId = row?.player_id != null ? Number(row.player_id) : null

  const openProfile = async () => {
    if (playerId == null) return
    setBusy(true)
    setError(null)
    try {
      useDashboardStore.getState().addWidgets([await createProfileWidget(playerId)])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not open profile')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <DataTable
        columns={spec.data.columns}
        hiddenColumns={['player_id']}
        rows={spec.data.rows}
        selectable={selectable}
        selectedIndex={selected}
        onSelect={(r, index) => {
          setSelected(index)
          if (spec.interactions.linkedEntity === 'player' && r.player_id != null) {
            eventBus.emit({
              event: 'PLAYER_SELECTED',
              entity: { type: 'PLAYER', id: String(r.player_id), label: String(r.player) },
              sourceWidgetId: spec.id,
            })
          }
        }}
      />
      {playerId != null && (
        <div className="flex items-center gap-2 p-2 text-xs">
          <button disabled={busy} onClick={openProfile} className="rounded bg-emerald-700 px-2 py-1 hover:bg-emerald-600 disabled:opacity-50">
            Show {String(row?.player)} profile
          </button>
          {error && <span className="text-red-400">{error}</span>}
        </div>
      )}
    </div>
  )
}
