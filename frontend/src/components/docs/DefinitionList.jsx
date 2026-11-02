import { Badge } from '../ui'

export function DefinitionList({ items = [], className = '' }) {
  return (
    <div className={`my-6 divide-y divide-line/60 rounded-2xl border border-line bg-elevated shadow-card ${className}`}>
      {items.map((item) => (
        <div
          key={item.term}
          id={`term-${item.term.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}
          className="p-5 transition-colors hover:bg-overlay/40 scroll-mt-24"
        >
          <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
            <dt className="text-base font-semibold tracking-[-0.015em] text-ink">
              {item.term}
            </dt>
            {item.category && (
              <Badge tone="accent">
                {item.category}
              </Badge>
            )}
          </div>
          <dd className="prose-note text-sm leading-relaxed text-muted">
            {item.definition}
          </dd>
          {item.example && (
            <div className="mt-2 text-xs text-faint">
              <span className="font-semibold text-ink">Example: </span>
              <span>{item.example}</span>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
