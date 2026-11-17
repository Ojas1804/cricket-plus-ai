import { useState } from 'react'
import { DataTable } from '../../components/common/DataTable'
import { eventBus } from '../../interactions/eventBus'
import type { WidgetComponentProps } from '../types'

export function TableWidget({ spec }: WidgetComponentProps) {
  const [selected, setSelected] = useState<number | null>(null)
  return (
    <DataTable
      columns={spec.data.columns}
      hiddenColumns={['player_id']}
      rows={spec.data.rows}
      selectable={spec.interactions.selectableRows}
      selectedIndex={selected}
      onSelect={(r, index) => {
        setSelected(index)
        if (r.player_id != null) {
          eventBus.emit({
            event: 'PLAYER_SELECTED',
            entity: { type: 'PLAYER', id: String(r.player_id), label: String(r.player) },
            sourceWidgetId: spec.id,
          })
        }
      }}
    />
  )
}
