import { ArrowRight, CornerDownLeft, FileText, Hash, Search, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

export function DocsSearch({ sections = [], className = '' }) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const inputRef = useRef(null)
  const navigate = useNavigate()

  // Build client-side search index
  const searchIndex = useMemo(() => {
    const items = []
    sections.forEach((sec) => {
      // Index section title & summary
      items.push({
        id: sec.id,
        sectionId: sec.id,
        headingId: null,
        title: sec.title,
        group: sec.group,
        type: 'section',
        content: `${sec.title} ${sec.summary}`,
      })

      // Index section blocks (headings, paragraphs, definitions, steps)
      sec.blocks?.forEach((block) => {
        if (block.type === 'heading') {
          items.push({
            id: `${sec.id}-${block.id}`,
            sectionId: sec.id,
            headingId: block.id,
            title: block.text,
            group: sec.title,
            type: 'heading',
            content: block.text,
          })
        } else if (block.type === 'paragraph' && block.text) {
          items.push({
            id: `${sec.id}-${Math.random().toString(36).substr(2, 6)}`,
            sectionId: sec.id,
            headingId: null,
            title: sec.title,
            group: sec.group,
            type: 'content',
            content: block.text,
          })
        } else if (block.type === 'definition-list' && block.items) {
          block.items.forEach((item) => {
            items.push({
              id: `${sec.id}-term-${item.term}`,
              sectionId: sec.id,
              headingId: `term-${item.term.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`,
              title: item.term,
              group: 'Glossary',
              type: 'term',
              content: `${item.term} ${item.definition}`,
            })
          })
        }
      })
    })
    return items
  }, [sections])

  // Filter and rank matches
  const results = useMemo(() => {
    if (!query.trim()) return []
    const q = query.toLowerCase().trim()
    const terms = q.split(/\s+/).filter(Boolean)

    return searchIndex
      .map((item) => {
        const titleLower = item.title.toLowerCase()
        const contentLower = item.content.toLowerCase()

        let score = 0
        if (titleLower === q) score += 100
        else if (titleLower.startsWith(q)) score += 50
        else if (titleLower.includes(q)) score += 30

        const matchesAll = terms.every((t) => contentLower.includes(t))
        if (!matchesAll) return null

        terms.forEach((t) => {
          if (titleLower.includes(t)) score += 20
          if (contentLower.includes(t)) score += 5
        })

        return { item, score }
      })
      .filter(Boolean)
      .sort((a, b) => b.score - a.score)
      .slice(0, 8)
      .map((entry) => entry.item)
  }, [searchIndex, query])

  // Keyboard shortcut "/" to focus search, Escape to close
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (
        e.key === '/' &&
        document.activeElement?.tagName !== 'INPUT' &&
        document.activeElement?.tagName !== 'TEXTAREA'
      ) {
        e.preventDefault()
        setOpen(true)
      } else if (e.key === 'Escape' && open) {
        setOpen(false)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [open])

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 50)
      setSelectedIndex(0)
    } else {
      setQuery('')
    }
  }, [open])

  // Arrow key navigation
  const handleInputKeyDown = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSelectedIndex((prev) => (prev + 1 < results.length ? prev + 1 : 0))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSelectedIndex((prev) => (prev > 0 ? prev - 1 : results.length - 1))
    } else if (e.key === 'Enter' && results[selectedIndex]) {
      e.preventDefault()
      selectResult(results[selectedIndex])
    }
  }

  const selectResult = (result) => {
    const path = result.headingId
      ? `/documentation/${result.sectionId}#${result.headingId}`
      : `/documentation/${result.sectionId}`
    navigate(path)
    setOpen(false)
  }

  const highlightMatches = (text, q) => {
    if (!q || !text) return text
    const words = q.trim().split(/\s+/).filter(Boolean)
    const regex = new RegExp(`(${words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'gi')
    const parts = text.split(regex)
    return parts.map((part, i) =>
      regex.test(part) ? (
        <mark key={i} className="bg-accent/25 text-ink font-semibold rounded px-0.5">
          {part}
        </mark>
      ) : (
        part
      )
    )
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={`flex items-center justify-between gap-3 rounded-xl border border-line bg-surface/70 px-3.5 py-2 text-xs text-faint transition-all hover:border-accent/40 hover:text-ink ${className}`}
        aria-label="Search documentation"
      >
        <span className="flex items-center gap-2">
          <Search className="h-3.5 w-3.5" />
          <span>Search documentation...</span>
        </span>
        <kbd className="mono rounded border border-line bg-elevated px-1.5 py-0.5 text-[0.68rem] font-medium text-muted">
          /
        </kbd>
      </button>

      {open && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-start justify-center bg-sand-950/45 p-4 pt-16 sm:pt-24 backdrop-blur-sm"
          onClick={() => setOpen(false)}
        >
          <div
            className="w-full max-w-lg rounded-2xl border border-line bg-elevated shadow-card overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center border-b border-line px-4 py-3">
              <Search className="h-4 w-4 shrink-0 text-faint" />
              <input
                ref={inputRef}
                type="text"
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value)
                  setSelectedIndex(0)
                }}
                onKeyDown={handleInputKeyDown}
                placeholder="Search concepts, CLI commands, guides..."
                className="w-full bg-transparent px-3 text-sm text-ink placeholder:text-faint focus:outline-none"
              />
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-lg p-1 text-faint hover:bg-overlay hover:text-ink"
                aria-label="Close search"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="max-h-80 overflow-y-auto p-2">
              {query && results.length === 0 ? (
                <div className="p-6 text-center text-xs text-faint">
                  <p className="font-semibold text-muted">No results found for &ldquo;{query}&rdquo;</p>
                  <p className="mt-1">Try searching for keywords like &ldquo;mock&rdquo;, &ldquo;dataset&rdquo;, &ldquo;evaluator&rdquo;, or &ldquo;metrics&rdquo;.</p>
                </div>
              ) : null}

              {!query ? (
                <div className="p-4 text-xs text-faint">
                  <p className="font-semibold text-muted mb-2">Quick Navigation</p>
                  <div className="space-y-1">
                    {sections.slice(0, 4).map((sec) => (
                      <div
                        key={sec.id}
                        onClick={() => selectResult({ sectionId: sec.id })}
                        className="flex cursor-pointer items-center justify-between rounded-lg p-2 hover:bg-overlay text-muted hover:text-ink"
                      >
                        <span className="flex items-center gap-2">
                          <FileText className="h-3.5 w-3.5 text-accent" />
                          <span>{sec.title}</span>
                        </span>
                        <ArrowRight className="h-3 w-3 text-faint" />
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {results.map((res, idx) => {
                const isSelected = selectedIndex === idx
                return (
                  <div
                    key={res.id}
                    onClick={() => selectResult(res)}
                    onMouseEnter={() => setSelectedIndex(idx)}
                    className={`flex cursor-pointer items-start justify-between gap-3 rounded-xl p-3 transition-colors ${
                      isSelected ? 'bg-accent-soft/70 text-ink' : 'text-muted hover:bg-overlay/60'
                    }`}
                  >
                    <div className="min-w-0 flex-1 space-y-1">
                      <div className="flex items-center gap-1.5 text-xs text-faint">
                        <span>{res.group}</span>
                        {res.headingId ? (
                          <>
                            <span>/</span>
                            <span className="flex items-center gap-1">
                              <Hash className="h-2.5 w-2.5 text-accent" />
                              <span>{res.headingId}</span>
                            </span>
                          </>
                        ) : null}
                      </div>
                      <h5 className="text-sm font-semibold text-ink">
                        {highlightMatches(res.title, query)}
                      </h5>
                      {res.type === 'content' && (
                        <p className="line-clamp-2 text-xs text-muted">
                          {highlightMatches(res.content, query)}
                        </p>
                      )}
                    </div>
                    {isSelected && (
                      <CornerDownLeft className="h-4 w-4 shrink-0 text-accent self-center" />
                    )}
                  </div>
                )
              })}
            </div>

            <div className="flex items-center justify-between border-t border-line/60 bg-surface/50 px-4 py-2 text-[0.7rem] text-faint">
              <span>Use <kbd className="mono font-semibold">↑</kbd> <kbd className="mono font-semibold">↓</kbd> to navigate, <kbd className="mono font-semibold">Enter</kbd> to select</span>
              <span><kbd className="mono font-semibold">Esc</kbd> to exit</span>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
