import { Component, Suspense, type ErrorInfo, type ReactNode } from 'react'
import type { WidgetSpec } from '../types/widget'
import { widgetRegistry } from './registry'

class WidgetErrorBoundary extends Component<{ children: ReactNode }, { error: string | null }> {
  state = { error: null as string | null }
  static getDerivedStateFromError(e: Error) {
    return { error: e.message }
  }
  componentDidCatch(e: Error, info: ErrorInfo) {
    console.error('Widget render failed', e.message, info.componentStack)
  }
  render() {
    return this.state.error
      ? <p className="p-3 text-sm text-red-400">This widget failed to render: {this.state.error}</p>
      : this.props.children
  }
}

export function WidgetRenderer({ spec, expanded }: { spec: WidgetSpec; expanded: boolean }) {
  const Impl = widgetRegistry[spec.type]
  if (!Impl) return <p className="p-3 text-sm text-amber-400">Unsupported widget type: "{spec.type}"</p>
  return (
    <WidgetErrorBoundary>
      <Suspense fallback={<p className="p-3 text-sm text-slate-400">Loading...</p>}>
        <Impl spec={spec} expanded={expanded} />
      </Suspense>
    </WidgetErrorBoundary>
  )
}
