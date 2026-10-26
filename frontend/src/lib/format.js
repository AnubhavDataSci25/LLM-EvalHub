/** Display helpers. Anything unmeasured renders as an em dash, never as 0. */

export const NA = '—'

export const pct = (value, digits = 1) =>
  value === null || value === undefined || Number.isNaN(value)
    ? NA
    : `${(value * 100).toFixed(digits)}%`

export const score = (value, digits = 2) =>
  value === null || value === undefined || Number.isNaN(value) ? NA : Number(value).toFixed(digits)

export const ms = (value) => {
  if (value === null || value === undefined || Number.isNaN(value)) return NA
  if (value < 1000) return `${Math.round(value)} ms`
  return `${(value / 1000).toFixed(2)} s`
}

export const seconds = (value) =>
  value === null || value === undefined ? NA : value < 60 ? `${value.toFixed(1)}s` : `${Math.floor(value / 60)}m ${Math.round(value % 60)}s`

export const num = (value) =>
  value === null || value === undefined ? NA : new Intl.NumberFormat().format(value)

export const titleCase = (value) =>
  (value || '').replace(/[_-]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

export const relativeTime = (iso) => {
  if (!iso) return NA
  const then = new Date(iso).getTime()
  const diff = Date.now() - then
  const mins = Math.round(diff / 60000)
  if (Number.isNaN(mins)) return NA
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  if (days < 30) return `${days}d ago`
  return new Date(iso).toLocaleDateString()
}

export const dateTime = (iso) => (iso ? new Date(iso).toLocaleString() : NA)

export const truncate = (text, length = 140) =>
  !text ? '' : text.length > length ? `${text.slice(0, length)}…` : text

/** Colour band for a 0-1 quality score. */
export const scoreTone = (value) => {
  if (value === null || value === undefined) return 'neutral'
  if (value >= 0.8) return 'good'
  if (value >= 0.6) return 'fair'
  if (value >= 0.4) return 'poor'
  return 'bad'
}

export const deltaTone = (direction) =>
  ({ improved: 'good', regressed: 'bad', unchanged: 'neutral' }[direction] || 'neutral')

export const metricKindLabel = (kind) =>
  ({
    deterministic: 'Deterministic',
    llm_judge: 'LLM judge',
    ragas: 'RAGAS',
    performance: 'Measured',
  }[kind] || titleCase(kind))

export const formatP = (value) => {
  if (value === null || value === undefined || Number.isNaN(value)) return NA
  if (value < 0.001) return '<0.001'
  return Number(value).toFixed(3)
}

export const formatCI = (low, high, digits = 2) => {
  if (
    low === null ||
    low === undefined ||
    high === null ||
    high === undefined ||
    Number.isNaN(low) ||
    Number.isNaN(high)
  )
    return NA
  const l = Number(low).toFixed(digits)
  const h = Number(high).toFixed(digits)
  return `[${low > 0 ? '+' : ''}${l}, ${high > 0 ? '+' : ''}${h}]`
}

export const formatKappa = (value) =>
  value === null || value === undefined || Number.isNaN(value) ? NA : Number(value).toFixed(2)

export const kappaTone = (value) => {
  if (value === null || value === undefined || Number.isNaN(value)) return 'neutral'
  if (value >= 0.6) return 'good'
  if (value >= 0.4) return 'fair'
  if (value >= 0.2) return 'poor'
  return 'bad'
}

export const attributionTone = (verdict) => {
  switch (verdict) {
    case 'RETRIEVAL_CAUSED':
      return 'fair'
    case 'GENERATION_CAUSED':
      return 'bad'
    case 'PARAMETRIC_KNOWLEDGE':
      return 'poor'
    case 'NOT_CONTEXT_DEPENDENT':
      return 'neutral'
    case 'NOT_ATTRIBUTABLE':
    default:
      return 'neutral'
  }
}

export const attributionLabel = (verdict) => {
  switch (verdict) {
    case 'RETRIEVAL_CAUSED':
      return 'Retrieval-caused'
    case 'GENERATION_CAUSED':
      return 'Generation-caused'
    case 'PARAMETRIC_KNOWLEDGE':
      return 'Parametric knowledge'
    case 'NOT_CONTEXT_DEPENDENT':
      return 'Not context-dependent'
    case 'NOT_ATTRIBUTABLE':
      return 'Not attributable'
    default:
      return titleCase(verdict)
  }
}
