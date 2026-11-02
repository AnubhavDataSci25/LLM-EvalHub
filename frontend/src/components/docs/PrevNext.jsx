import { ArrowLeft, ArrowRight, ArrowUp } from 'lucide-react'
import { Link } from 'react-router-dom'

export function PrevNext({ prev, next }) {
  if (!prev && !next) return null

  return (
    <nav
      aria-label="Documentation section navigation"
      className="border-t border-line/70 pt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 w-full"
    >
      {prev ? (
        <Link
          to={`/documentation/${prev.id}`}
          className="group relative flex flex-col justify-between rounded-2xl border border-line bg-elevated p-4 sm:p-5 shadow-card transition-all hover:border-accent/40 hover:shadow-lift min-w-0 w-full overflow-hidden text-left"
        >
          <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-faint transition-colors group-hover:text-accent">
            <ArrowLeft className="h-3.5 w-3.5 shrink-0 transition-transform group-hover:-translate-x-1" />
            <span>Previous</span>
          </span>
          <span className="mt-2.5 block text-sm font-semibold text-ink transition-colors group-hover:text-accent leading-snug break-words">
            {prev.title}
          </span>
        </Link>
      ) : null}

      {next ? (
        <Link
          to={`/documentation/${next.id}`}
          className={`group relative flex flex-col justify-between rounded-2xl border border-line bg-elevated p-4 sm:p-5 shadow-card transition-all hover:border-accent/40 hover:shadow-lift min-w-0 w-full overflow-hidden text-right items-end ${
            !prev ? 'sm:col-start-2' : ''
          }`}
        >
          <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-faint transition-colors group-hover:text-accent">
            <span>Next</span>
            <ArrowRight className="h-3.5 w-3.5 shrink-0 transition-transform group-hover:translate-x-1" />
          </span>
          <span className="mt-2.5 block w-full text-sm font-semibold text-ink transition-colors group-hover:text-accent leading-snug break-words">
            {next.title}
          </span>
        </Link>
      ) : null}
    </nav>
  )
}

export function BackToTop() {
  const scrollToTop = () => {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  return (
    <button
      type="button"
      onClick={scrollToTop}
      className="inline-flex items-center gap-1.5 rounded-xl border border-line bg-elevated px-3 py-1.5 text-xs font-semibold text-faint transition-all hover:border-accent/40 hover:text-ink hover:shadow-card focus:outline-none shrink-0"
      title="Back to top of page"
    >
      <ArrowUp className="h-3.5 w-3.5 shrink-0" />
      <span>Back to top</span>
    </button>
  )
}
