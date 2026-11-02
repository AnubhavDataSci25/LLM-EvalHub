import { Check, Copy, Hash } from 'lucide-react'
import { useState } from 'react'

export function HeadingAnchor({ id, level = 2, children, className = '' }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = (e) => {
    e.preventDefault()
    const url = `${window.location.origin}${window.location.pathname}#${id}`
    navigator.clipboard?.writeText(url)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
    window.history.pushState(null, '', `#${id}`)
  }

  const Tag = level === 3 ? 'h3' : 'h2'
  const sizeClass =
    level === 3
      ? 'text-lg font-semibold tracking-[-0.015em] text-ink mt-8 mb-3'
      : 'text-2xl font-semibold tracking-[-0.025em] text-ink mt-12 mb-4 border-b border-line/60 pb-2'

  return (
    <Tag id={id} className={`group relative flex items-center gap-2 scroll-mt-24 ${sizeClass} ${className}`}>
      <span>{children}</span>
      <a
        href={`#${id}`}
        onClick={handleCopy}
        aria-label={`Copy link to ${typeof children === 'string' ? children : id}`}
        className="inline-flex h-6 w-6 items-center justify-center rounded-md text-faint opacity-0 transition-all duration-150 group-hover:opacity-100 hover:bg-overlay hover:text-accent focus:opacity-100 focus:outline-none"
        title={copied ? 'Link copied!' : 'Copy link to heading'}
      >
        {copied ? (
          <Check className="h-3.5 w-3.5 text-[rgb(var(--ok))]" />
        ) : (
          <Hash className="h-3.5 w-3.5" />
        )}
      </a>
      {copied && (
        <span className="text-xs font-normal text-[rgb(var(--ok))] animate-fade-in">
          Copied!
        </span>
      )}
    </Tag>
  )
}
