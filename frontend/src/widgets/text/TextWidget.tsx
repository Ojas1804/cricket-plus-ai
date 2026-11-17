import type { WidgetComponentProps } from '../types'

export function TextWidget({ spec }: WidgetComponentProps) {
  return <p className="p-3 text-sm leading-relaxed text-slate-200">{String(spec.data.extra.text ?? '')}</p>
}
