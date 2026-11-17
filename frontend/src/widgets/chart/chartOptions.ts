type Extra = Record<string, unknown>
type Row = Record<string, unknown>

const label = (s: unknown) => (s ? String(s).replace(/_/g, ' ') : undefined)
const legendStyle = { top: 0, textStyle: { color: '#cbd5e1' } }

export function buildOption(extra: Extra, rows: Row[]): Record<string, unknown> {
  const base = { backgroundColor: 'transparent' }
  const chartType = String(extra.chartType ?? 'line')
  const slices = extra.slices as { name: string; value: number }[] | undefined
  const points = extra.points as { name: string; value: [number, number] }[] | undefined
  const indicators = extra.indicators as { name: string; max: number }[] | undefined
  const radarSeries = extra.radarSeries as { name: string; value: number[] }[] | undefined
  const cells = extra.cells as [number, number, number][] | undefined

  if (chartType === 'pie' && slices) {
    return { ...base, tooltip: { trigger: 'item' }, series: [{ type: 'pie', radius: ['30%', '70%'], data: slices }] }
  }
  if (chartType === 'radar' && indicators && radarSeries) {
    return {
      ...base, tooltip: {}, legend: { ...legendStyle, data: radarSeries.map((s) => s.name) },
      radar: { indicator: indicators, radius: '62%', center: ['50%', '56%'] },
      series: [{ type: 'radar', data: radarSeries, areaStyle: { opacity: 0.15 } }],
    }
  }
  if (chartType === 'heatmap' && cells) {
    return {
      ...base, tooltip: { position: 'top' },
      grid: { left: 90, right: 16, top: 16, bottom: 64 },
      xAxis: { type: 'category', data: extra.xCategories, splitArea: { show: true } },
      yAxis: { type: 'category', data: extra.yCategories, splitArea: { show: true } },
      visualMap: {
        min: extra.min, max: extra.max, calculable: true, orient: 'horizontal', left: 'center', bottom: 0,
        textStyle: { color: '#cbd5e1' }, inRange: { color: ['#1e293b', '#059669', '#fde047'] },
      },
      series: [{ type: 'heatmap', data: cells, label: { show: true }, emphasis: { itemStyle: { shadowBlur: 8 } } }],
    }
  }
  if (chartType === 'scatter' && points) {
    return {
      ...base, tooltip: { formatter: (p: { name: string; value: number[] }) => `${p.name}<br/>${p.value[0]}, ${p.value[1]}` },
      grid: { left: 56, right: 16, top: 24, bottom: 40 },
      xAxis: { type: 'value', name: label(extra.xLabel), nameLocation: 'middle', nameGap: 24, scale: true },
      yAxis: { type: 'value', name: label(extra.yLabel), scale: true },
      series: [{ type: 'scatter', symbolSize: 12, data: points }],
    }
  }
  const x = String(extra.x ?? 'x')
  const y = String(extra.y ?? 'y')
  const categories = extra.categories as string[] | undefined
  const series = extra.series as { name: string; data: unknown[] }[] | undefined
  const type = chartType === 'bar' ? 'bar' : 'line'
  return {
    ...base, tooltip: { trigger: 'axis' },
    grid: { left: 56, right: 16, top: 32, bottom: 28 },
    legend: series && series.length > 1 ? legendStyle : undefined,
    xAxis: { type: 'category', data: categories ?? rows.map((r) => String(r[x])) },
    yAxis: { type: 'value', name: label(extra.yLabel) },
    series: (series ?? [{ name: y, data: rows.map((r) => r[y]) }]).map((s) => ({ ...s, type, smooth: true })),
  }
}
