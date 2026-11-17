export interface GridItem { i: string; x: number; y: number; w: number; h: number }

export const FULL_COLS = 12

export function colsForWidth(width: number): number {
  return width >= 996 ? FULL_COLS : width >= 600 ? 6 : 2
}

const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), hi)

/** Derives a narrower-breakpoint layout from the canonical 12-column layout. Widths scale; phones stack in reading order. */
export function layoutForCols(items: GridItem[], cols: number): GridItem[] {
  if (cols >= FULL_COLS) return items
  const sorted = [...items].sort((a, b) => a.y - b.y || a.x - b.x)
  if (cols <= 2) {
    let y = 0
    return sorted.map((it) => {
      const out = { ...it, x: 0, y, w: cols }
      y += it.h
      return out
    })
  }
  return sorted.map((it) => {
    const w = clamp(Math.round((it.w * cols) / FULL_COLS), Math.min(2, cols), cols)
    return { ...it, w, x: clamp(Math.round((it.x * cols) / FULL_COLS), 0, cols - w) }
  })
}
