import { expect, test } from 'vitest'
import { colsForWidth, layoutForCols, type GridItem } from './layout'

const items: GridItem[] = [
  { i: 'a', x: 0, y: 0, w: 6, h: 8 }, { i: 'b', x: 6, y: 0, w: 6, h: 6 }, { i: 'c', x: 0, y: 8, w: 12, h: 4 },
]

test('breakpoints', () => {
  expect([1400, 996, 800, 600, 400].map(colsForWidth)).toEqual([12, 12, 6, 6, 2])
})

test('desktop layout is untouched', () => {
  expect(layoutForCols(items, 12)).toBe(items)
})

test('tablet layout scales widths and positions and stays inside the grid', () => {
  const out = layoutForCols(items, 6)
  expect(out.find((i) => i.i === 'a')).toMatchObject({ x: 0, w: 3 })
  expect(out.find((i) => i.i === 'b')).toMatchObject({ x: 3, w: 3 })
  expect(out.find((i) => i.i === 'c')).toMatchObject({ x: 0, w: 6 })
  for (const i of out) expect(i.x + i.w).toBeLessThanOrEqual(6)
})

test('phone layout stacks widgets full width in reading order without overlap', () => {
  const out = layoutForCols(items, 2)
  expect(out.map((i) => i.i)).toEqual(['a', 'b', 'c'])
  expect(out.map((i) => i.y)).toEqual([0, 8, 14])
  expect(out.every((i) => i.x === 0 && i.w === 2)).toBe(true)
})

test('does not mutate the canonical layout', () => {
  const copy = JSON.parse(JSON.stringify(items))
  layoutForCols(items, 2)
  layoutForCols(items, 6)
  expect(items).toEqual(copy)
})
