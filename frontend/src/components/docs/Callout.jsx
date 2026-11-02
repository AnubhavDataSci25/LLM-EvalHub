import { AlertTriangle, CheckCircle2, Info, Lightbulb, ShieldCheck } from 'lucide-react'

const CONFIGS = {
  info: {
    icon: Info,
    toneClass: 'border-[rgb(var(--info))]/30 bg-[rgb(var(--info))]/8 text-ink',
    iconClass: 'text-[rgb(var(--info))]',
    defaultTitle: 'Note',
  },
  warning: {
    icon: AlertTriangle,
    toneClass: 'border-[rgb(var(--warn))]/35 bg-[rgb(var(--warn))]/10 text-ink',
    iconClass: 'text-[rgb(var(--warn))]',
    defaultTitle: 'Warning',
  },
  tip: {
    icon: Lightbulb,
    toneClass: 'border-accent/30 bg-accent-soft/50 text-ink',
    iconClass: 'text-accent',
    defaultTitle: 'Tip',
  },
  honesty: {
    icon: ShieldCheck,
    toneClass: 'border-[rgb(var(--ok))]/30 bg-[rgb(var(--ok))]/10 text-ink',
    iconClass: 'text-[rgb(var(--ok))]',
    defaultTitle: 'Honesty Note',
  },
  success: {
    icon: CheckCircle2,
    toneClass: 'border-[rgb(var(--ok))]/30 bg-[rgb(var(--ok))]/10 text-ink',
    iconClass: 'text-[rgb(var(--ok))]',
    defaultTitle: 'Success',
  },
}

export function Callout({ tone = 'info', title, body, children, className = '' }) {
  const conf = CONFIGS[tone] || CONFIGS.info
  const Icon = conf.icon

  return (
    <div
      role="note"
      className={`my-5 rounded-2xl border p-4.5 text-sm leading-relaxed shadow-sm transition-colors ${conf.toneClass} ${className}`}
    >
      <div className="flex items-start gap-3">
        <span className={`mt-0.5 shrink-0 ${conf.iconClass}`}>
          <Icon className="h-4.5 w-4.5" />
        </span>
        <div className="min-w-0 flex-1 space-y-1.5">
          <p className="font-semibold tracking-[-0.01em] text-ink">
            {title || conf.defaultTitle}
          </p>
          {body && <p className="text-muted leading-relaxed">{body}</p>}
          {children && <div className="text-muted leading-relaxed">{children}</div>}
        </div>
      </div>
    </div>
  )
}
