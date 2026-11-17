import { useMemo } from 'react'
import ReactGridLayout, { useContainerWidth, type Layout } from 'react-grid-layout'
import { RESIZABLE_TYPES, useDashboardStore } from '../stores/dashboardStore'
import { FULL_COLS, colsForWidth, layoutForCols, type GridItem } from './layout'
import { MARGIN, ROW_HEIGHT, WidgetFrame } from './WidgetFrame'

const COLLAPSED_H = 2

export function Dashboard() {
  const { width, containerRef, mounted } = useContainerWidth()
  const widgets = useDashboardStore((s) => s.widgets)
  const order = useDashboardStore((s) => s.order)
  const hydrated = useDashboardStore((s) => s.hydrated)
  const setLayout = useDashboardStore((s) => s.setLayout)
  const cols = colsForWidth(width)

  const layout: Layout = useMemo(() => {
    const items: GridItem[] = order.map((id) => {
      const { layout: l, expanded } = widgets[id]
      return { i: id, x: l.x, y: l.y, w: l.w, h: expanded ? l.h : COLLAPSED_H }
    })
    return layoutForCols(items, cols).map((it) => {
      const { spec, expanded } = widgets[it.i]
      return { ...it, minW: Math.min(2, cols), minH: 3, isResizable: expanded && RESIZABLE_TYPES.has(spec.type) }
    })
  }, [order, widgets, cols])

  const persist = (next: Layout) => {
    if (cols !== FULL_COLS) return
    setLayout(next.filter((n) => widgets[n.i]?.expanded).map((n) => ({ i: n.i, x: n.x, y: n.y, w: n.w, h: n.h })))
  }

  if (!order.length) {
    return (
      <p className="py-16 text-center text-slate-500">
        {hydrated ? 'Ask a question above to create your first widget.' : 'Restoring your workspace...'}
      </p>
    )
  }

  return (
    <div ref={containerRef}>
      {mounted && (
        <ReactGridLayout
          layout={layout}
          width={width}
          gridConfig={{ cols, rowHeight: ROW_HEIGHT, margin: [MARGIN, MARGIN] }}
          dragConfig={{ enabled: true, handle: '.widget-drag-handle' }}
          resizeConfig={{ enabled: true }}
          onDragStop={persist}
          onResizeStop={persist}
        >
          {order.map((id) => (
            <div key={id}><WidgetFrame state={widgets[id]} /></div>
          ))}
        </ReactGridLayout>
      )}
    </div>
  )
}
