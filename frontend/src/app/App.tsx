import { Download } from 'lucide-react'
import { useEffect } from 'react'
import { PromptBar } from '../components/prompt/PromptBar'
import { Dashboard } from '../dashboard/Dashboard'
import { dashboardToJson, download } from '../export/exporters'
import { startLinking } from '../interactions/linking'
import { createDefaultStore } from '../persistence/kvStore'
import { hydrateApp } from '../persistence/persistence'
import { attachWidgets, focusWidget } from '../services/api'
import { useDashboardStore } from '../stores/dashboardStore'

export default function App() {
  const hasWidgets = useDashboardStore((s) => s.order.length > 0)

  useEffect(() => startLinking(focusWidget), [])
  useEffect(() => {
    let stop: (() => void) | undefined
    let cancelled = false
    hydrateApp(createDefaultStore(), attachWidgets).then((s) => (cancelled ? s() : (stop = s)))
    return () => { cancelled = true; stop?.() }
  }, [])

  const exportDashboard = () => {
    const { widgets, order } = useDashboardStore.getState()
    download('cricket-canvas-dashboard.json', 'application/json', dashboardToJson(widgets, order))
  }

  return (
    <div className="min-h-screen p-3 sm:p-4">
      <header className="relative mb-6 text-center">
        <h1 className="text-xl font-bold tracking-tight sm:text-2xl">Cricket Canvas</h1>
        <p className="text-sm text-slate-400">Ask. Visualize. Arrange.</p>
        {hasWidgets && (
          <button onClick={exportDashboard} title="Export dashboard"
            className="absolute right-0 top-0 flex items-center gap-1 rounded border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800">
            <Download size={14} /><span className="hidden sm:inline">Export dashboard</span>
          </button>
        )}
      </header>
      <PromptBar />
      <main className="mt-6"><Dashboard /></main>
    </div>
  )
}
