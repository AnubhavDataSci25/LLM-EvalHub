import { CheckCircle2 } from 'lucide-react'

export function StepList({ steps = [], className = '' }) {
  return (
    <div className={`my-6 space-y-6 ${className}`}>
      {steps.map((step, idx) => (
        <div
          key={step.title || idx}
          className="relative flex items-start gap-4 rounded-2xl border border-line/70 bg-elevated/70 p-5 shadow-card transition-all"
        >
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-accent text-accent-ink text-xs font-bold tracking-tight shadow-sm">
            {String(idx + 1).padStart(2, '0')}
          </div>
          <div className="min-w-0 flex-1 space-y-2">
            <h4 className="text-base font-semibold tracking-[-0.015em] text-ink">
              {step.title}
            </h4>
            {step.body && (
              <div className="prose-note text-sm leading-relaxed text-muted">
                {step.body}
              </div>
            )}
            {step.code && (
              <div className="my-2">
                {typeof step.code === 'string' ? (
                  <pre className="mono overflow-x-auto rounded-xl border border-line bg-surface p-3 text-xs text-ink">
                    <code>{step.code}</code>
                  </pre>
                ) : (
                  step.code
                )}
              </div>
            )}
            {step.expected && (
              <div className="mt-3 flex items-start gap-2 rounded-xl border border-[rgb(var(--ok))]/25 bg-[rgb(var(--ok))]/8 px-3.5 py-2 text-xs text-ink">
                <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[rgb(var(--ok))]" />
                <div className="leading-snug">
                  <span className="font-semibold text-[rgb(var(--ok))]">Expected result: </span>
                  <span className="text-muted">{step.expected}</span>
                </div>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
