import { useMutation } from '@tanstack/react-query'
import { History, Send, X } from 'lucide-react'
import { useState } from 'react'
import { submitPrompt } from '../../services/api'
import { useDashboardStore } from '../../stores/dashboardStore'
import { useHistoryStore } from '../../stores/historyStore'

export const SUGGESTED_PROMPTS = [
  { category: 'Player statistics', prompt: 'Show the top 10 IPL run scorers' },
  { category: 'Player comparisons', prompt: 'Compare Virat Kohli and Rohit Sharma' },
  { category: 'Team statistics', prompt: "Compare India and Australia's win percentage" },
  { category: 'Advanced analytics', prompt: 'Compare Virat Kohli and Rohit Sharma and show their performance trends' },
  { category: 'Live cricket', prompt: 'Show all live international matches' },
  { category: 'Historical analysis', prompt: 'Show the evolution of batting strike rates in T20 cricket' },
]

export function PromptBar() {
  const [text, setText] = useState('')
  const [notice, setNotice] = useState<string | null>(null)
  const [showHistory, setShowHistory] = useState(false)
  const [cursor, setCursor] = useState(-1)
  const store = useDashboardStore()
  const history = useHistoryStore()
  const target = store.updateTargetId ? store.widgets[store.updateTargetId] : null

  const mutation = useMutation({
    mutationFn: ({ prompt, targetId }: { prompt: string; targetId: string | null }) =>
      submitPrompt(prompt, targetId ? 'UPDATE' : 'ADD', targetId),
    onSuccess: (res, { prompt, targetId }) => {
      history.add({
        prompt, action: targetId ? 'UPDATE' : 'ADD', targetWidgetId: targetId,
        status: res.status === 'CLARIFICATION_REQUIRED' ? 'CLARIFICATION_REQUIRED' : 'COMPLETED', widgetIds: res.widgets.map((w) => w.id),
      })
      setNotice(res.status === 'CLARIFICATION_REQUIRED' ? (res.message ?? 'Could you clarify your request?') : null)
      if (res.status === 'CLARIFICATION_REQUIRED') {
        if (targetId) store.setStatus(targetId, 'READY')
        return
      }
      if (targetId) res.widgets.forEach((w) => store.replaceSpec(targetId, w))
      else store.addWidgets(res.widgets)
      store.setUpdateTarget(null)
      setText('')
      setCursor(-1)
    },
    onError: (e, { prompt, targetId }) => {
      history.add({ prompt, action: targetId ? 'UPDATE' : 'ADD', targetWidgetId: targetId, status: 'FAILED', widgetIds: [] })
      if (targetId) store.setStatus(targetId, 'ERROR', e.message)
    },
  })

  const submit = (prompt: string) => {
    if (!prompt.trim() || mutation.isPending) return
    const targetId = store.updateTargetId
    if (targetId) store.setStatus(targetId, 'PLANNING')
    mutation.mutate({ prompt, targetId })
  }

  const recall = (direction: 1 | -1) => {
    const prompts = history.entries.map((e) => e.prompt)
    const next = Math.min(Math.max(cursor + direction, -1), prompts.length - 1)
    setCursor(next)
    setText(next === -1 ? '' : prompts[next])
  }

  return (
    <section className="mx-auto max-w-3xl space-y-3">
      {target && (
        <div className="flex items-center justify-between rounded bg-emerald-900/40 px-3 py-1 text-sm">
          <span>Updating: <strong>{target.spec.title}</strong></span>
          <button onClick={() => store.setUpdateTarget(null)} aria-label="Cancel update"><X size={14} /></button>
        </div>
      )}
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); submit(text) }}>
        <input
          value={text}
          onChange={(e) => { setText(e.target.value); setCursor(-1) }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowUp') { e.preventDefault(); recall(1) }
            if (e.key === 'ArrowDown') { e.preventDefault(); recall(-1) }
          }}
          placeholder={target ? 'Describe how to change this widget...' : 'Ask anything about cricket...'}
          className="min-w-0 flex-1 rounded-lg border border-slate-700 bg-slate-900 px-4 py-2.5 outline-none focus:border-emerald-500"
        />
        <button type="button" onClick={() => setShowHistory((v) => !v)} aria-label="Query history" title="Query history"
          className="rounded-lg border border-slate-700 px-3 hover:bg-slate-800"><History size={16} /></button>
        <button disabled={mutation.isPending} className="rounded-lg bg-emerald-600 px-4 hover:bg-emerald-500 disabled:opacity-50" aria-label="Submit">
          <Send size={16} />
        </button>
      </form>
      {showHistory && (
        <div className="rounded-lg border border-slate-700 bg-slate-900 p-2 text-sm">
          <div className="mb-1 flex items-center justify-between text-xs text-slate-400">
            <span>Recent queries</span>
            {history.entries.length > 0 && <button onClick={history.clear} className="hover:text-slate-200">Clear</button>}
          </div>
          {history.entries.length === 0 && <p className="py-2 text-center text-slate-500">No queries yet.</p>}
          <ul className="max-h-56 overflow-auto">
            {history.entries.slice(0, 20).map((h) => (
              <li key={h.id} className="flex items-center gap-2 rounded px-2 py-1 hover:bg-slate-800">
                <button className="min-w-0 flex-1 truncate text-left" onClick={() => { setText(h.prompt); setShowHistory(false) }}>{h.prompt}</button>
                <span className={`text-xs ${h.status === 'COMPLETED' ? 'text-emerald-500' : h.status === 'FAILED' ? 'text-red-400' : 'text-amber-400'}`}>
                  {h.action === 'UPDATE' ? 'update' : h.status === 'COMPLETED' ? 'ok' : h.status === 'FAILED' ? 'failed' : 'clarify'}
                </span>
                <button className="text-xs text-slate-400 hover:text-slate-100" onClick={() => submit(h.prompt)}>Run again</button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {notice && <p className="rounded bg-amber-900/40 px-3 py-2 text-sm text-amber-200">{notice}</p>}
      {mutation.isError && !target && <p className="text-sm text-red-400">{mutation.error.message}</p>}
      <div className="flex flex-wrap gap-2">
        {SUGGESTED_PROMPTS.map((s) => (
          <button key={s.prompt} title={s.category} onClick={() => submit(s.prompt)}
            className="rounded-full border border-slate-700 px-3 py-1 text-xs text-slate-300 hover:bg-slate-800">
            {s.prompt}
          </button>
        ))}
      </div>
    </section>
  )
}
