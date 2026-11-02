import { useEffect, useState } from 'react'

export function DocsOutline({ headings = [] }) {
  const [activeId, setActiveId] = useState('')

  useEffect(() => {
    if (!headings.length) return

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.find((entry) => entry.isIntersecting)
        if (visible) {
          setActiveId(visible.target.id)
        }
      },
      {
        rootMargin: '-80px 0px -60% 0px',
        threshold: 0.1,
      }
    )

    headings.forEach((h) => {
      const el = document.getElementById(h.id)
      if (el) observer.observe(el)
    })

    return () => observer.disconnect()
  }, [headings])

  if (!headings.length) return null

  return (
    <aside className="sticky top-20 hidden w-64 shrink-0 overflow-y-auto px-4 py-6 xl:block max-h-[calc(100vh-5rem)]">
      <p className="label mb-3">On this page</p>
      <nav className="space-y-1 text-xs">
        {headings.map((h) => {
          const isActive = activeId === h.id
          return (
            <a
              key={h.id}
              href={`#${h.id}`}
              onClick={(e) => {
                e.preventDefault()
                const el = document.getElementById(h.id)
                if (el) {
                  el.scrollIntoView({ behavior: 'smooth' })
                  window.history.pushState(null, '', `#${h.id}`)
                  setActiveId(h.id)
                }
              }}
              className={`block rounded-lg py-1.5 transition-colors break-words leading-snug ${
                h.level === 3 ? 'pl-4 pr-2' : 'pl-2 pr-2'
              } ${
                isActive
                  ? 'bg-accent/10 font-semibold text-accent'
                  : 'text-muted hover:text-ink hover:bg-overlay/60'
              }`}
            >
              {h.text}
            </a>
          )
        })}
      </nav>
    </aside>
  )
}
