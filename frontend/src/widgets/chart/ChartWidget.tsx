import { BarChart, HeatmapChart, LineChart, PieChart, RadarChart, ScatterChart } from 'echarts/charts'
import { GridComponent, LegendComponent, RadarComponent, TooltipComponent, VisualMapComponent } from 'echarts/components'
import * as echarts from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { useEffect, useRef } from 'react'
import type { WidgetComponentProps } from '../types'
import { buildOption } from './chartOptions'

echarts.use([
  LineChart, BarChart, PieChart, ScatterChart, RadarChart, HeatmapChart,
  GridComponent, TooltipComponent, LegendComponent, RadarComponent, VisualMapComponent, CanvasRenderer,
])

export function ChartWidget({ spec }: WidgetComponentProps) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!ref.current) return
    const chart = echarts.init(ref.current, 'dark', { renderer: 'canvas' })
    chart.setOption(buildOption(spec.data.extra, spec.data.rows))
    const observer = new ResizeObserver(() => chart.resize())
    observer.observe(ref.current)
    return () => { observer.disconnect(); chart.dispose() }
  }, [spec])

  return <div ref={ref} className="h-full min-h-48 w-full" />
}
