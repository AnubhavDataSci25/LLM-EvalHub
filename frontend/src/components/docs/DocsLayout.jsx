import { AnimatePresence, motion } from 'framer-motion'
import { ArrowLeft, BookOpen, Menu, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'

import { ThemeToggle } from '../layout/AppLayout'
import { DocsOutline } from './DocsOutline'
import { DocsSearch } from './DocsSearch'
import { DocsSidebar } from './DocsSidebar'

const APP_VERSION = '1.0.0'
const LAST_UPDATED = 'November 2026'

export function DocsLayout({ groups = [], sections = [], currentSection, headings = [], children }) {
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false)
  const location = useLocation()

  useEffect(() => {
    setMobileDrawerOpen(false)
  }, [location.pathname])

  return (
    <div className="relative z-[1] min-h-screen bg-surface text-ink flex flex-col">
      {/* Top Header */}
      <header className="sticky top-0 z-30 border-b border-line bg-surface/85 backdrop-blur-md print:hidden">
        <div className="mx-auto flex h-14 max-w-[1500px] items-center justify-between gap-3 px-4 sm:px-6">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setMobileDrawerOpen(true)}
              className="rounded-xl border border-line bg-elevated p-2 text-muted transition-colors hover:text-ink lg:hidden"
              aria-label="Open documentation navigation"
            >
              <Menu className="h-4 w-4" />
            </button>

            <Link to="/documentation" className="flex items-center gap-2.5">
              <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-accent text-accent-ink shadow-card">
                <BookOpen className="h-4 w-4" />
              </span>
              <span className="text-[1.05rem] font-semibold tracking-[-0.02em]">
                LLM<span className="text-accent">-</span>EvalHub <span className="text-muted font-normal text-sm">Docs</span>
              </span>
            </Link>

            <span className="hidden sm:inline-flex items-center rounded-full border border-line bg-overlay px-2 py-0.5 text-[0.68rem] font-semibold text-muted">
              v{APP_VERSION}
            </span>
          </div>

          {/* Search in header on desktop */}
          <div className="hidden md:block flex-1 max-w-sm mx-4">
            <DocsSearch sections={sections} className="w-full" />
          </div>

          <div className="flex items-center gap-2.5">
            <Link
              to="/dashboard"
              className="flex items-center gap-1.5 rounded-xl border border-line bg-elevated px-3 py-1.5 text-xs font-semibold text-muted hover:border-accent/40 hover:text-ink transition-colors"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Back to App</span>
            </Link>
            <ThemeToggle />
          </div>
        </div>
      </header>

      {/* Mobile Search Bar below header */}
      <div className="md:hidden border-b border-line/60 bg-overlay/30 px-4 py-2.5 print:hidden">
        <DocsSearch sections={sections} className="w-full" />
      </div>

      {/* Main 3-column layout */}
      <div className="mx-auto flex w-full max-w-[1500px] flex-1 items-start">
        {/* Left column: Desktop Sidebar */}
        <aside className="sticky top-14 hidden h-[calc(100vh-3.5rem)] w-64 shrink-0 flex-col border-r border-line bg-elevated/40 backdrop-blur lg:flex print:hidden">
          <DocsSidebar groups={groups} />
        </aside>

        {/* Mobile Navigation Drawer */}
        <AnimatePresence>
          {mobileDrawerOpen ? (
            <>
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="fixed inset-0 z-40 bg-sand-950/45 backdrop-blur-sm lg:hidden"
                onClick={() => setMobileDrawerOpen(false)}
              />
              <motion.aside
                initial={{ x: -280 }}
                animate={{ x: 0 }}
                exit={{ x: -280 }}
                transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
                className="fixed inset-y-0 left-0 z-50 flex w-72 flex-col border-r border-line bg-elevated lg:hidden"
              >
                <div className="flex items-center justify-between border-b border-line px-4 py-3.5">
                  <span className="text-sm font-semibold text-ink">Documentation</span>
                  <button
                    onClick={() => setMobileDrawerOpen(false)}
                    className="rounded-lg p-1.5 text-faint hover:bg-overlay hover:text-ink"
                    aria-label="Close navigation"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
                <DocsSidebar groups={groups} onNavigate={() => setMobileDrawerOpen(false)} />
              </motion.aside>
            </>
          ) : null}
        </AnimatePresence>

        {/* Center column: Main Reading Content */}
        <main className="min-w-0 flex-1 px-4 py-8 sm:px-8 lg:px-12 print:px-0 print:py-0">
          <div className="mx-auto max-w-[72ch]">
            {/* Metadata Bar */}
            <div className="mb-6 flex flex-wrap items-center justify-between gap-2 text-xs text-faint border-b border-line/60 pb-3 print:hidden">
              <div className="flex items-center gap-2">
                <span className="font-medium text-accent">{currentSection?.group || 'Documentation'}</span>
                <span>/</span>
                <span>{currentSection?.title}</span>
              </div>
              <div className="flex items-center gap-3">
                <span>Updated: {LAST_UPDATED}</span>
                <span>•</span>
                <span>Version {APP_VERSION}</span>
              </div>
            </div>

            {children}
          </div>
        </main>

        {/* Right column: "On this page" outline */}
        <DocsOutline headings={headings} />
      </div>

      {/* Footer */}
      <footer className="border-t border-line/80 px-4 py-6 text-xs text-faint print:hidden">
        <div className="mx-auto flex max-w-[1500px] flex-wrap items-center justify-between gap-3 px-4 sm:px-6">
          <span>LLM-EvalHub Documentation · Version {APP_VERSION}</span>
          <div className="flex items-center gap-4">
            <a href="/docs" target="_blank" rel="noreferrer" className="text-accent hover:underline">
              API Reference
            </a>
            <Link to="/dashboard" className="text-muted hover:text-ink">
              Dashboard
            </Link>
          </div>
        </div>
      </footer>
    </div>
  )
}
