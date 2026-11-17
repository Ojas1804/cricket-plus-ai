import { DataTable } from '../../components/common/DataTable'
import type { WidgetComponentProps } from '../types'

export function ComparisonWidget({ spec }: WidgetComponentProps) {
  return <DataTable columns={spec.data.columns} rows={spec.data.rows} />
}
