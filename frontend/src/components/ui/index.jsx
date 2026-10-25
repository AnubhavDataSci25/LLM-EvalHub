/**
 * Shared UI primitives.
 *
 * Every screen in the app is built from these, which is what keeps spacing,
 * radius, motion and colour consistent across seventeen pages.
 */
import { motion } from 'framer-motion'
import {
  AlertTriangle,
  Check,
  ChevronDown,
  Info,
  Loader2,
  RefreshCw,
  X,
} from 'lucide-react'
import { createContext, useContext, useEffect, useId, useState } from 'react'

import { NA } from '../../lib/format'

/* ------------------------------------------------------------------ motion */
export const fadeUp = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.42, ease: [0.22, 1, 0.36, 1] },
}

export const stagger = {
  animate: { transition: { staggerChildren: 0.05 } },
}

export function Reveal({ children, delay = 0, className = '' }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.5, delay, ease: [0.22, 1, 0.36, 1] }}
      className={className}
    >
      {children}
    </motion.div>
  )
}

/* ------------------------------------------------------------------ layout */
export function Card({ children, className = '', hover = false, as: Tag = 'div', ...rest }) {
  return (
    <Tag className={`card ${hover ? 'card-hover' : ''} ${className}`} {...rest}>
      {children}
    </Tag>
  )
}

export function SectionHeader({ title, description, actions, icon: Icon }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <div className="flex items-center gap-2.5">
          {Icon ? <Icon className="h-[1.15rem] w-[1.15rem] shrink-0 text-accent" /> : null}
          <h2 className="text-xl font-semibold tracking-[-0.02em]">{title}</h2>
        </div>
        {description ? <p className="prose-note mt-1.5 max-w-2xl">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  )
}

export function PageHeader({ eyebrow, title, description, actions, children }) {
  return (
    <motion.header {...fadeUp} className="mb-8">
      <div className="flex flex-wrap items-start justify-between gap-5">
        <div className="min-w-0 flex-1">
          {eyebrow ? <p className="label mb-2">{eyebrow}</p> : null}
          <h1 className="text-[1.9rem] font-semibold leading-tight tracking-[-0.03em] sm:text-[2.2rem]">
            {title}
          </h1>
          {description ? (
            <p className="prose-note mt-2.5 max-w-3xl text-[0.95rem]">{description}</p>
          ) : null}
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      {children}
    </motion.header>
  )
}

/* ------------------------------------------------------------------ badges */
const TONES = {
  good: 'bg-[rgb(var(--ok))]/12 text-[rgb(var(--ok))] border-[rgb(var(--ok))]/25',
  fair: 'bg-[rgb(var(--warn))]/12 text-[rgb(var(--warn))] border-[rgb(var(--warn))]/25',
  poor: 'bg-clay-500/12 text-clay-500 border-clay-500/25',
  bad: 'bg-[rgb(var(--bad))]/12 text-[rgb(var(--bad))] border-[rgb(var(--bad))]/25',
  info: 'bg-[rgb(var(--info))]/12 text-[rgb(var(--info))] border-[rgb(var(--info))]/25',
  accent: 'bg-accent-soft text-accent border-accent/25',
  neutral: 'bg-overlay text-muted border-line',
}

export function Badge({ tone = 'neutral', children, className = '', icon: Icon }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-1
                  text-[0.72rem] font-semibold ${TONES[tone] || TONES.neutral} ${className}`}
    >
      {Icon ? <Icon className="h-3 w-3" /> : null}
      {children}
    </span>
  )
}

const STATUS_TONES = {
  completed: 'good',
  running: 'info',
  queued: 'neutral',
  failed: 'bad',
  error: 'bad',
  indexed: 'good',
  uploaded: 'neutral',
  ready: 'good',
  configured: 'good',
  not_configured: 'neutral',
}

export function StatusBadge({ status, className = '' }) {
  const tone = STATUS_TONES[status] || 'neutral'
  const spinning = status === 'running' || status === 'queued'
  return (
    <Badge tone={tone} className={className}>
      <span
        className={`h-1.5 w-1.5 rounded-full bg-current ${spinning ? 'animate-pulse' : ''}`}
      />
      {(status || 'unknown').replace(/_/g, ' ')}
    </Badge>
  )
}

/* ------------------------------------------------------------------ buttons */
export function Button({
  variant = 'secondary',
  loading = false,
  icon: Icon,
  children,
  className = '',
  ...rest
}) {
  const variants = {
    primary: 'btn-primary',
    secondary: 'btn-secondary',
    ghost: 'btn-ghost',
    danger: 'btn-danger',
  }
  return (
    <button
      className={`${variants[variant] || variants.secondary} ${className}`}
      disabled={loading || rest.disabled}
      {...rest}
    >
      {loading ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : Icon ? (
        <Icon className="h-4 w-4" />
      ) : null}
      {children}
    </button>
  )
}

/* ------------------------------------------------------------------ inputs */
export function Field({ label, hint, error, children, required }) {
  return (
    <label className="block">
      <span className="mb-1.5 flex items-center gap-1.5 text-sm font-semibold text-ink">
        {label}
        {required ? <span className="text-[rgb(var(--bad))]">*</span> : null}
      </span>
      {children}
      {error ? (
        <span className="mt-1.5 block text-xs text-[rgb(var(--bad))]">{error}</span>
      ) : hint ? (
        <span className="mt-1.5 block text-xs text-faint">{hint}</span>
      ) : null}
    </label>
  )
}

export function Input(props) {
  return <input className="input" {...props} />
}

export function Textarea({ rows = 4, ...props }) {
  return <textarea rows={rows} className="input resize-y leading-relaxed" {...props} />
}

export function Select({ options = [], placeholder, ...props }) {
  return (
    <div className="relative">
      <select className="input appearance-none pr-9" {...props}>
        {placeholder ? <option value="">{placeholder}</option> : null}
        {options.map((opt) =>
          typeof opt === 'string' ? (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ) : (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ),
        )}
      </select>
      <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
    </div>
  )
}

export function Toggle({ checked, onChange, label, description, disabled }) {
  const id = useId()
  return (
    <div className="flex items-start gap-3">
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={`relative mt-0.5 h-6 w-11 shrink-0 rounded-full border transition-all duration-300 ease-spring
                    disabled:opacity-50 ${
                      checked ? 'border-accent bg-accent' : 'border-line bg-overlay'
                    }`}
      >
        <span
          className={`absolute top-1/2 h-4 w-4 -translate-y-1/2 rounded-full bg-elevated shadow transition-all
                      duration-300 ease-spring ${checked ? 'left-6' : 'left-1'}`}
        />
      </button>
      <label htmlFor={id} className="cursor-pointer select-none">
        <span className="block text-sm font-semibold text-ink">{label}</span>
        {description ? <span className="prose-note block text-xs">{description}</span> : null}
      </label>
    </div>
  )
}

export function Checkbox({ checked, onChange, label, description, disabled }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`flex w-full items-start gap-3 rounded-xl border p-3 text-left transition-all duration-200
                  ease-spring disabled:opacity-50 ${
                    checked
                      ? 'border-accent/60 bg-accent-soft/60 shadow-card'
                      : 'border-line bg-surface hover:border-accent/35 hover:bg-overlay/60'
                  }`}
    >
      <span
        className={`mt-0.5 flex h-[1.1rem] w-[1.1rem] shrink-0 items-center justify-center rounded-md border
                    transition-all duration-200 ${
                      checked ? 'border-accent bg-accent text-accent-ink' : 'border-line bg-elevated'
                    }`}
      >
        {checked ? <Check className="h-3 w-3" strokeWidth={3} /> : null}
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-semibold text-ink">{label}</span>
        {description ? (
          <span className="prose-note mt-0.5 block text-xs leading-snug">{description}</span>
        ) : null}
      </span>
    </button>
  )
}

/* ------------------------------------------------------------------ tabs */
export function Tabs({ tabs, active, onChange, className = '' }) {
  return (
    <div className={`flex gap-1 overflow-x-auto rounded-xl border border-line bg-overlay/60 p-1 ${className}`}>
      {tabs.map((tab) => {
        const value = tab.value ?? tab
        const label = tab.label ?? tab
        const isActive = active === value
        return (
          <button
            key={value}
            onClick={() => onChange(value)}
            className={`relative shrink-0 rounded-lg px-3.5 py-2 text-sm font-semibold transition-colors duration-200
                        ${isActive ? 'text-accent-ink' : 'text-muted hover:text-ink'}`}
          >
            {isActive ? (
              <motion.span
                layoutId="tab-pill"
                className="absolute inset-0 rounded-lg bg-accent shadow-card"
                transition={{ type: 'spring', stiffness: 380, damping: 32 }}
              />
            ) : null}
            <span className="relative z-10 flex items-center gap-1.5">
              {label}
              {tab.count !== undefined ? (
                <span className={`text-[0.7rem] ${isActive ? 'opacity-80' : 'text-faint'}`}>
                  {tab.count}
                </span>
              ) : null}
            </span>
          </button>
        )
      })}
    </div>
  )
}

/* ------------------------------------------------------------------ states */
export function Spinner({ className = 'h-5 w-5' }) {
  return <Loader2 className={`animate-spin text-accent ${className}`} />
}

export function LoadingState({ label = 'Loading…', rows = 3 }) {
  return (
    <div className="space-y-3" role="status" aria-live="polite">
      <div className="flex items-center gap-2.5 text-sm text-muted">
        <Spinner className="h-4 w-4" />
        {label}
      </div>
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="skeleton h-16 w-full" />
      ))}
    </div>
  )
}

export function EmptyState({ icon: Icon = Info, title, description, action, compact = false }) {
  return (
    <motion.div
      {...fadeUp}
      className={`flex flex-col items-center justify-center rounded-2xl border border-dashed border-line
                  bg-overlay/35 text-center ${compact ? 'px-6 py-8' : 'px-8 py-14'}`}
    >
      <span className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl border border-line bg-elevated text-accent">
        <Icon className="h-5 w-5" />
      </span>
      <h3 className="text-base font-semibold text-ink">{title}</h3>
      {description ? (
        <p className="prose-note mt-2 max-w-md text-sm">{description}</p>
      ) : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </motion.div>
  )
}

export function ErrorState({ error, onRetry, compact = false }) {
  const message = error?.message || String(error || 'Something went wrong.')
  const code = error?.code
  const hint =
    error?.isConfiguration
      ? 'Add the provider key to the backend .env file and restart the API.'
      : error?.isTransient
        ? 'This usually resolves on its own — try again in a moment.'
        : null
  return (
    <motion.div
      {...fadeUp}
      role="alert"
      className={`rounded-2xl border border-[rgb(var(--bad))]/30 bg-[rgb(var(--bad))]/8 ${
        compact ? 'p-4' : 'p-6'
      }`}
    >
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-[rgb(var(--bad))]" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-ink">{message}</p>
          {code ? <p className="mono mt-1 text-xs text-faint">{code}</p> : null}
          {hint ? <p className="prose-note mt-2 text-xs">{hint}</p> : null}
          {onRetry ? (
            <Button variant="secondary" icon={RefreshCw} className="mt-3" onClick={onRetry}>
              Try again
            </Button>
          ) : null}
        </div>
      </div>
    </motion.div>
  )
}

export function InlineNote({ tone = 'info', icon: Icon = Info, children }) {
  const tones = {
    info: 'border-[rgb(var(--info))]/28 bg-[rgb(var(--info))]/8',
    warn: 'border-[rgb(var(--warn))]/28 bg-[rgb(var(--warn))]/8',
    bad: 'border-[rgb(var(--bad))]/28 bg-[rgb(var(--bad))]/8',
    accent: 'border-accent/28 bg-accent-soft/60',
  }
  return (
    <div className={`flex items-start gap-2.5 rounded-xl border px-3.5 py-3 ${tones[tone]}`}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted" />
      <div className="prose-note text-[0.82rem] leading-relaxed">{children}</div>
    </div>
  )
}

/* ------------------------------------------------------------------ progress */
export function ProgressBar({ value = 0, label, showValue = true, tone = 'accent' }) {
  const percent = Math.max(0, Math.min(100, (value || 0) * 100))
  const colours = {
    accent: 'bg-accent',
    good: 'bg-[rgb(var(--ok))]',
    warn: 'bg-[rgb(var(--warn))]',
    bad: 'bg-[rgb(var(--bad))]',
  }
  return (
    <div>
      {label || showValue ? (
        <div className="mb-1.5 flex items-center justify-between text-xs text-muted">
          <span>{label}</span>
          {showValue ? <span className="mono">{percent.toFixed(0)}%</span> : null}
        </div>
      ) : null}
      <div className="h-2 overflow-hidden rounded-full bg-overlay">
        <motion.div
          className={`h-full rounded-full ${colours[tone]}`}
          initial={{ width: 0 }}
          animate={{ width: `${percent}%` }}
          transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        />
      </div>
    </div>
  )
}

export function ScoreBar({ value, tone = 'accent' }) {
  if (value === null || value === undefined) {
    return <span className="text-faint">{NA}</span>
  }
  const colours = {
    good: 'bg-[rgb(var(--ok))]',
    fair: 'bg-[rgb(var(--warn))]',
    poor: 'bg-clay-500',
    bad: 'bg-[rgb(var(--bad))]',
    accent: 'bg-accent',
    neutral: 'bg-faint',
  }
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-14 overflow-hidden rounded-full bg-overlay">
        <motion.div
          className={`h-full rounded-full ${colours[tone] || colours.accent}`}
          initial={{ width: 0 }}
          animate={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }}
          transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
        />
      </div>
      <span className="mono tabular-nums">{value.toFixed(2)}</span>
    </div>
  )
}

/* ------------------------------------------------------------------ modal */
export function Modal({ open, onClose, title, description, children, footer, size = 'md' }) {
  useEffect(() => {
    if (!open) return undefined
    const handler = (event) => event.key === 'Escape' && onClose?.()
    document.addEventListener('keydown', handler)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', handler)
      document.body.style.overflow = ''
    }
  }, [open, onClose])

  if (!open) return null
  const widths = { sm: 'max-w-md', md: 'max-w-2xl', lg: 'max-w-4xl' }
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto p-4 sm:p-8">
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="fixed inset-0 bg-sand-950/45 backdrop-blur-sm"
        onClick={onClose}
      />
      <motion.div
        initial={{ opacity: 0, y: 16, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
        className={`relative z-10 my-auto w-full ${widths[size]} rounded-2xl border border-line bg-elevated shadow-lift`}
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-start justify-between gap-4 border-b border-line px-6 py-4">
          <div className="min-w-0">
            <h3 className="text-lg font-semibold">{title}</h3>
            {description ? <p className="prose-note mt-1 text-sm">{description}</p> : null}
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-faint transition-colors hover:bg-overlay hover:text-ink"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="max-h-[65vh] overflow-y-auto px-6 py-5">{children}</div>
        {footer ? (
          <div className="flex flex-wrap justify-end gap-2 border-t border-line px-6 py-4">
            {footer}
          </div>
        ) : null}
      </motion.div>
    </div>
  )
}

/* ------------------------------------------------------------------ toasts */
const ToastContext = createContext(null)

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const push = (toast) => {
    const id = Math.random().toString(36).slice(2)
    setToasts((current) => [...current, { id, ...toast }])
    setTimeout(() => setToasts((current) => current.filter((t) => t.id !== id)), toast.duration || 5000)
  }

  const value = {
    success: (message, title) => push({ tone: 'good', message, title }),
    error: (message, title) => push({ tone: 'bad', message, title }),
    info: (message, title) => push({ tone: 'info', message, title }),
  }

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed bottom-5 right-5 z-[60] flex w-[min(24rem,calc(100vw-2.5rem))] flex-col gap-2.5">
        {toasts.map((toast) => (
          <motion.div
            key={toast.id}
            initial={{ opacity: 0, x: 24, scale: 0.97 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: 24 }}
            transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
            className="pointer-events-auto rounded-xl border border-line bg-elevated px-4 py-3 shadow-lift"
          >
            <div className="flex items-start gap-2.5">
              <span
                className={`mt-1 h-2 w-2 shrink-0 rounded-full ${
                  { good: 'bg-[rgb(var(--ok))]', bad: 'bg-[rgb(var(--bad))]', info: 'bg-[rgb(var(--info))]' }[
                    toast.tone
                  ]
                }`}
              />
              <div className="min-w-0 flex-1">
                {toast.title ? (
                  <p className="text-sm font-semibold text-ink">{toast.title}</p>
                ) : null}
                <p className="prose-note text-[0.82rem] leading-snug">{toast.message}</p>
              </div>
              <button
                onClick={() => setToasts((c) => c.filter((t) => t.id !== toast.id))}
                className="text-faint transition-colors hover:text-ink"
                aria-label="Dismiss"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          </motion.div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const context = useContext(ToastContext)
  if (!context) throw new Error('useToast must be used inside a ToastProvider')
  return context
}

/* ------------------------------------------------------------------ misc */
export function Copyable({ value, className = '' }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      onClick={() => {
        navigator.clipboard?.writeText(value)
        setCopied(true)
        setTimeout(() => setCopied(false), 1600)
      }}
      className={`mono inline-flex items-center gap-1.5 rounded-md bg-overlay px-2 py-0.5 text-xs text-muted
                  transition-colors hover:text-ink ${className}`}
      title="Copy to clipboard"
    >
      {value}
      {copied ? <Check className="h-3 w-3 text-[rgb(var(--ok))]" /> : null}
    </button>
  )
}

export function KeyValue({ items, columns = 2 }) {
  return (
    <dl className={`grid gap-x-6 gap-y-3.5 ${columns === 2 ? 'sm:grid-cols-2' : ''}`}>
      {items
        .filter((item) => item)
        .map((item) => (
          <div key={item.label} className="min-w-0">
            <dt className="label mb-1">{item.label}</dt>
            <dd className="break-words text-sm text-ink">{item.value ?? NA}</dd>
          </div>
        ))}
    </dl>
  )
}
