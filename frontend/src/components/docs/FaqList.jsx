import { ChevronDown } from 'lucide-react'
import { useState } from 'react'

export function FaqList({ items = [], className = '' }) {
  const [openIdx, setOpenIdx] = useState(null)

  const toggle = (idx) => {
    setOpenIdx(openIdx === idx ? null : idx)
  }

  return (
    <div className={`my-6 space-y-3 ${className}`}>
      {items.map((item, idx) => {
        const isOpen = openIdx === idx
        return (
          <div
            key={item.question || idx}
            className="rounded-2xl border border-line bg-elevated shadow-card overflow-hidden transition-all"
          >
            <button
              type="button"
              onClick={() => toggle(idx)}
              className="flex w-full items-center justify-between p-4.5 text-left transition-colors hover:bg-overlay/40"
              aria-expanded={isOpen}
            >
              <span className="text-sm font-semibold text-ink">{item.question}</span>
              <ChevronDown
                className={`h-4 w-4 shrink-0 text-faint transition-transform duration-200 ${
                  isOpen ? 'rotate-180 text-accent' : ''
                }`}
              />
            </button>
            {isOpen && (
              <div className="border-t border-line/60 bg-surface/50 p-4.5 text-sm leading-relaxed text-muted space-y-2">
                {item.answer && <p>{item.answer}</p>}
                {item.fix && (
                  <div className="rounded-xl border border-[rgb(var(--ok))]/25 bg-[rgb(var(--ok))]/8 p-3 text-xs text-ink">
                    <span className="font-semibold text-[rgb(var(--ok))]">Recommended fix: </span>
                    <span className="text-muted">{item.fix}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
