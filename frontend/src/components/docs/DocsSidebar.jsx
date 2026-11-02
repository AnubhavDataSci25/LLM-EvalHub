import { BookOpen, ExternalLink, FileCode, Layers } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { getApiDocUrls } from '../../lib/api'

export function DocsSidebar({ groups = [], onNavigate }) {
  const docUrls = getApiDocUrls()

  return (
    <nav className="flex-1 space-y-6 overflow-y-auto px-4 py-6" aria-label="Documentation Navigation">
      {groups.map((group) => (
        <div key={group.name} className="space-y-1">
          <p className="label mb-2 px-2 text-[0.7rem]">{group.name}</p>
          <div className="space-y-0.5">
            {group.sections.map((sec) => (
              <NavLink
                key={sec.id}
                to={`/documentation/${sec.id}`}
                onClick={onNavigate}
                className={({ isActive }) =>
                  `group flex items-center justify-between gap-2 min-w-0 rounded-xl px-3 py-2 text-xs font-medium transition-colors ${
                    isActive
                      ? 'border border-accent/25 bg-accent-soft/70 text-accent font-semibold'
                      : 'text-muted hover:bg-overlay/70 hover:text-ink'
                  }`
                }
              >
                <span className="truncate min-w-0">{sec.title}</span>
                {sec.badge && (
                  <span className="shrink-0 rounded bg-accent/15 px-1.5 py-0.5 text-[0.65rem] font-semibold text-accent uppercase">
                    {sec.badge}
                  </span>
                )}
              </NavLink>
            ))}
          </div>
        </div>
      ))}

      {/* Live API Documentation links */}
      <div className="border-t border-line/70 pt-5 mt-6 px-2 space-y-2">
        <p className="label mb-2 text-[0.7rem]">API Reference</p>
        <a
          href={docUrls.swagger}
          target="_blank"
          rel="noreferrer"
          className="flex items-center justify-between rounded-lg px-2.5 py-1.5 text-xs text-muted hover:bg-overlay hover:text-ink transition-colors"
        >
          <span className="flex items-center gap-2">
            <BookOpen className="h-3.5 w-3.5 text-accent" />
            <span>Interactive Swagger</span>
          </span>
          <ExternalLink className="h-3 w-3 text-faint" />
        </a>
        <a
          href={docUrls.redoc}
          target="_blank"
          rel="noreferrer"
          className="flex items-center justify-between rounded-lg px-2.5 py-1.5 text-xs text-muted hover:bg-overlay hover:text-ink transition-colors"
        >
          <span className="flex items-center gap-2">
            <Layers className="h-3.5 w-3.5 text-accent" />
            <span>ReDoc Specification</span>
          </span>
          <ExternalLink className="h-3 w-3 text-faint" />
        </a>
        <a
          href={docUrls.openapi}
          target="_blank"
          rel="noreferrer"
          className="flex items-center justify-between rounded-lg px-2.5 py-1.5 text-xs text-muted hover:bg-overlay hover:text-ink transition-colors"
        >
          <span className="flex items-center gap-2">
            <FileCode className="h-3.5 w-3.5 text-accent" />
            <span>OpenAPI (JSON)</span>
          </span>
          <ExternalLink className="h-3 w-3 text-faint" />
        </a>
      </div>
    </nav>
  )
}
