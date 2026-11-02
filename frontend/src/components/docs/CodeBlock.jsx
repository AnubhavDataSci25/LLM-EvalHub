import { Check, Copy, WrapText } from 'lucide-react'
import { useState } from 'react'

export function CodeBlock({ code = '', language = 'bash', filename, className = '' }) {
  const [copied, setCopied] = useState(false)
  const [wrap, setWrap] = useState(false)

  const handleCopy = () => {
    navigator.clipboard?.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className={`my-5 overflow-hidden rounded-2xl border border-line bg-elevated shadow-card ${className}`}>
      <div className="flex items-center justify-between border-b border-line/60 bg-overlay/60 px-4 py-2 text-xs">
        <div className="flex items-center gap-2">
          {filename ? (
            <span className="font-semibold text-ink">{filename}</span>
          ) : (
            <span className="font-medium uppercase tracking-wider text-faint">{language}</span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setWrap(!wrap)}
            className={`rounded-lg p-1.5 transition-colors ${
              wrap ? 'bg-accent/15 text-accent' : 'text-faint hover:bg-overlay hover:text-ink'
            }`}
            title={wrap ? 'Disable line wrap' : 'Enable line wrap'}
            aria-label={wrap ? 'Disable line wrap' : 'Enable line wrap'}
          >
            <WrapText className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={handleCopy}
            className="flex items-center gap-1 rounded-lg px-2 py-1 text-faint transition-colors hover:bg-overlay hover:text-ink"
            title="Copy code"
            aria-label="Copy code to clipboard"
          >
            {copied ? (
              <>
                <Check className="h-3.5 w-3.5 text-[rgb(var(--ok))]" />
                <span className="text-[0.7rem] text-[rgb(var(--ok))]">Copied</span>
              </>
            ) : (
              <>
                <Copy className="h-3.5 w-3.5" />
                <span className="text-[0.7rem]">Copy</span>
              </>
            )}
          </button>
        </div>
      </div>
      <div className="p-4">
        <pre
          className={`mono text-[0.82rem] leading-relaxed text-ink selection:bg-accent/20 ${
            wrap ? 'whitespace-pre-wrap break-words' : 'overflow-x-auto whitespace-pre'
          }`}
        >
          <code>{code}</code>
        </pre>
      </div>
    </div>
  )
}
