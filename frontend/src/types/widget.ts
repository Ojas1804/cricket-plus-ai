import { z } from 'zod'

export const WIDGET_TYPES = [
  'scorecard', 'leaderboard', 'table', 'chart', 'player_profile', 'comparison', 'text',
  'image', 'timeline', 'fixture', 'points_table', 'advanced_stats',
] as const

export const WidgetSpecSchema = z.object({
  schemaVersion: z.literal('1.0'),
  id: z.string(),
  type: z.string(),
  title: z.string(),
  description: z.string().default(''),
  query: z.record(z.string(), z.unknown()).default({}),
  data: z.object({
    columns: z.array(z.string()).default([]),
    rows: z.array(z.record(z.string(), z.unknown())).default([]),
    extra: z.record(z.string(), z.unknown()).default({}),
  }),
  metadata: z.object({
    source: z.string(),
    lastUpdated: z.string(),
    filters: z.record(z.string(), z.unknown()).default({}),
    coverage: z.record(z.string(), z.unknown()).default({}),
    isMock: z.boolean().default(false),
    provenance: z.record(z.string(), z.unknown()).default({}),
  }),
  interactions: z.object({
    selectableRows: z.boolean().default(false),
    linkedEntity: z.string().nullable().default(null),
    subscribesTo: z.array(z.string()).default([]),
  }).default({ selectableRows: false, linkedEntity: null, subscribesTo: [] }),
})

export const PromptResponseSchema = z.object({
  executionId: z.string(),
  status: z.enum(['COMPLETED', 'PENDING', 'FAILED', 'CLARIFICATION_REQUIRED']),
  widgets: z.array(WidgetSpecSchema),
  message: z.string().nullable().default(null),
  options: z.array(z.string()).default([]),
})

export type WidgetSpec = z.infer<typeof WidgetSpecSchema>
export type PromptResponse = z.infer<typeof PromptResponseSchema>
export type PromptAction = 'ADD' | 'UPDATE'

export type WidgetStatus =
  | 'CREATED' | 'PLANNING' | 'FETCHING' | 'COMPUTING' | 'RENDERING' | 'READY' | 'REFRESHING' | 'ERROR'

export interface GridPosition { x: number; y: number; w: number; h: number }

export interface WidgetState {
  spec: WidgetSpec
  status: WidgetStatus
  error?: string
  expanded: boolean
  linked: boolean
  layout: GridPosition
}
