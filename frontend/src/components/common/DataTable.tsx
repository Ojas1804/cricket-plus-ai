import { flexRender, getCoreRowModel, getSortedRowModel, useReactTable, type ColumnDef, type SortingState } from '@tanstack/react-table'
import { useMemo, useState } from 'react'

type Row = Record<string, unknown>

interface Props {
  columns: string[]
  rows: Row[]
  selectable?: boolean
  hiddenColumns?: string[]
  selectedIndex?: number | null
  onSelect?: (row: Row, index: number) => void
}

export function DataTable({ columns, rows, selectable, hiddenColumns = [], selectedIndex, onSelect }: Props) {
  const [sorting, setSorting] = useState<SortingState>([])
  const defs = useMemo<ColumnDef<Row>[]>(
    () => columns.filter((c) => !hiddenColumns.includes(c)).map((c) => ({ accessorKey: c, header: c.replace(/_/g, ' ') })),
    [columns, hiddenColumns.join(',')],
  )
  const table = useReactTable({
    data: rows, columns: defs, state: { sorting }, onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel(),
  })

  if (!rows.length) return <p className="p-3 text-sm text-slate-400">No data matches the current filters.</p>

  return (
    <table className="w-full text-left text-sm">
      <thead className="sticky top-0 bg-slate-900 text-xs uppercase text-slate-400">
        {table.getHeaderGroups().map((hg) => (
          <tr key={hg.id}>
            {hg.headers.map((h) => (
              <th key={h.id} className="cursor-pointer select-none px-3 py-2" onClick={h.column.getToggleSortingHandler()}>
                {flexRender(h.column.columnDef.header, h.getContext())}
                {{ asc: ' ▲', desc: ' ▼' }[h.column.getIsSorted() as string] ?? ''}
              </th>
            ))}
          </tr>
        ))}
      </thead>
      <tbody>
        {table.getRowModel().rows.map((r) => (
          <tr
            key={r.id}
            onClick={selectable ? () => onSelect?.(r.original, r.index) : undefined}
            className={`border-t border-slate-800 ${selectable ? 'cursor-pointer hover:bg-slate-800' : ''} ${selectedIndex === r.index ? 'bg-emerald-900/40' : ''}`}
          >
            {r.getVisibleCells().map((c) => (
              <td key={c.id} className="px-3 py-1.5">{String(c.getValue() ?? '')}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}
