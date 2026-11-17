import { PromptResponseSchema, WidgetSpecSchema, type PromptAction, type PromptResponse, type WidgetSpec } from '../types/widget'

const BASE = import.meta.env.VITE_API_BASE_URL ?? ''

async function request(path: string, init?: RequestInit): Promise<unknown> {
  const res = await fetch(`${BASE}/api/v1${path}`, { headers: { 'Content-Type': 'application/json' }, ...init })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail ?? `Request failed (${res.status})`)
  }
  return res.status === 204 ? null : res.json()
}

export async function submitPrompt(prompt: string, action: PromptAction, targetWidgetId: string | null): Promise<PromptResponse> {
  const json = await request('/prompts', { method: 'POST', body: JSON.stringify({ prompt, action, targetWidgetId }) })
  return PromptResponseSchema.parse(json)
}

export async function registerWidget(spec: WidgetSpec): Promise<WidgetSpec> {
  return WidgetSpecSchema.parse(await request('/widgets', { method: 'POST', body: JSON.stringify(spec) }))
}

export async function refreshWidget(id: string): Promise<WidgetSpec> {
  return WidgetSpecSchema.parse(await request(`/widgets/${id}/refresh`, { method: 'POST' }))
}

export async function fetchLiveWidget(matchId: string, widgetId: string): Promise<WidgetSpec> {
  return WidgetSpecSchema.parse(await request(`/matches/${encodeURIComponent(matchId)}/widget?widgetId=${encodeURIComponent(widgetId)}`))
}

export async function focusWidget(id: string, playerId: number): Promise<WidgetSpec> {
  const body = JSON.stringify({ entityType: 'PLAYER', entityId: playerId })
  return WidgetSpecSchema.parse(await request(`/widgets/${id}/focus`, { method: 'POST', body }))
}

export async function createProfileWidget(playerId: number): Promise<WidgetSpec> {
  return WidgetSpecSchema.parse(await request(`/players/${playerId}/profile-widget`, { method: 'POST' }))
}

export async function attachWidgets(specs: WidgetSpec[]): Promise<void> {
  for (let i = 0; i < specs.length; i += 100) {
    await request('/dashboard/widgets', { method: 'POST', body: JSON.stringify({ widgets: specs.slice(i, i + 100) }) })
  }
}

export async function removeWidget(id: string): Promise<void> {
  await request(`/widgets/${id}`, { method: 'DELETE' })
}
