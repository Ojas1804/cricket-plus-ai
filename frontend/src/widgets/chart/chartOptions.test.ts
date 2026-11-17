import { expect, test } from 'vitest'
import { buildOption } from './chartOptions'

type Opt = Record<string, any>

test('line and bar charts with series use categories and a legend only for multiple series', () => {
  const o = buildOption({ chartType: 'line', categories: ['2022', '2023'], series: [{ name: 'A', data: [1, 2] }, { name: 'B', data: [3, 4] }], yLabel: 'runs' }, []) as Opt
  expect(o.xAxis.data).toEqual(['2022', '2023'])
  expect(o.series.map((s: Opt) => s.type)).toEqual(['line', 'line'])
  expect(o.legend).toBeDefined()
  expect(o.yAxis.name).toBe('runs')
  const single = buildOption({ chartType: 'bar', categories: ['A'], series: [{ name: 'runs', data: [1] }] }, []) as Opt
  expect(single.legend).toBeUndefined()
  expect(single.series[0].type).toBe('bar')
})

test('legacy x/y row charts still render', () => {
  const o = buildOption({ chartType: 'line', x: 'year', y: 'runs' }, [{ year: 2020, runs: 5 }, { year: 2021, runs: 7 }]) as Opt
  expect(o.xAxis.data).toEqual(['2020', '2021'])
  expect(o.series[0].data).toEqual([5, 7])
})

test('radar chart exposes indicators and one series entry per entity', () => {
  const o = buildOption({
    chartType: 'radar', indicators: [{ name: 'runs', max: 10 }, { name: 'average', max: 5 }, { name: 'sr', max: 200 }],
    radarSeries: [{ name: 'A', value: [8, 4, 150] }, { name: 'B', value: [5, 3, 120] }],
  }, []) as Opt
  expect(o.radar.indicator).toHaveLength(3)
  expect(o.series[0].type).toBe('radar')
  expect(o.series[0].data).toHaveLength(2)
  expect(o.legend.data).toEqual(['A', 'B'])
})

test('heatmap uses categories, cells and a visual map with the data range', () => {
  const o = buildOption({ chartType: 'heatmap', xCategories: ['x1', 'x2'], yCategories: ['y1'], cells: [[0, 0, 3], [1, 0, 9]], min: 3, max: 9 }, []) as Opt
  expect(o.xAxis.data).toEqual(['x1', 'x2'])
  expect(o.yAxis.data).toEqual(['y1'])
  expect(o.visualMap).toMatchObject({ min: 3, max: 9 })
  expect(o.series[0]).toMatchObject({ type: 'heatmap', data: [[0, 0, 3], [1, 0, 9]] })
})

test('scatter and pie', () => {
  const s = buildOption({ chartType: 'scatter', points: [{ name: 'A', value: [1, 2] }], xLabel: 'runs', yLabel: 'strike_rate' }, []) as Opt
  expect(s.series[0].type).toBe('scatter')
  expect(s.yAxis.name).toBe('strike rate')
  const p = buildOption({ chartType: 'pie', slices: [{ name: 'A', value: 3 }] }, []) as Opt
  expect(p.series[0].type).toBe('pie')
})

test('a radar or heatmap without its data falls back to a standard chart instead of crashing', () => {
  const o = buildOption({ chartType: 'heatmap', categories: ['A'], series: [{ name: 'm', data: [1] }] }, []) as Opt
  expect(o.series[0].type).toBe('line')
})
