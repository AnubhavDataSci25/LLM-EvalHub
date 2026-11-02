import { ArrowRight, ExternalLink } from 'lucide-react'
import { Link } from 'react-router-dom'

export function LinkCard({ title, description, href, external = false, className = '' }) {
  const content = (
    <div className={`group flex items-start justify-between gap-4 rounded-2xl border border-line bg-elevated p-5 shadow-card transition-all duration-200 hover:border-accent/50 hover:shadow-lift ${className}`}>
      <div className="space-y-1">
        <h4 className="text-base font-semibold text-ink group-hover:text-accent transition-colors flex items-center gap-2">
          {title}
          {external ? <ExternalLink className="h-3.5 w-3.5 text-faint" /> : null}
        </h4>
        {description && <p className="prose-note text-sm text-muted">{description}</p>}
      </div>
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-line bg-surface text-faint group-hover:border-accent/40 group-hover:text-accent transition-colors">
        <ArrowRight className="h-4 w-4" />
      </div>
    </div>
  )

  if (external) {
    return (
      <a href={href} target="_blank" rel="noreferrer" className="block my-3">
        {content}
      </a>
    )
  }

  return (
    <Link to={href} className="block my-3">
      {content}
    </Link>
  )
}
