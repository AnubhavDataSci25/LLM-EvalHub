/** Application shell — sidebar navigation, topbar, theme toggle. */
import { AnimatePresence, motion } from 'framer-motion'
import {
  Activity,
  BarChart3,
  Beaker,
  BookOpen,
  Database,
  FileText,
  FlaskConical,
  GitCompare,
  LayoutDashboard,
  Lightbulb,
  Menu,
  Moon,
  Play,
  Scale,
  Settings,
  Sun,
  X,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'

import { useApi, useTheme } from '../../hooks'
import { api } from '../../lib/api'
import { Badge } from '../ui'

const NAV_SECTIONS = [
  {
    label: 'Overview',
    items: [
      { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
      { to: '/evaluations/new', label: 'New evaluation', icon: Play },
    ],
  },
  {
    label: 'Inputs',
    items: [
      { to: '/datasets', label: 'Datasets', icon: Database },
      { to: '/benchmarks', label: 'Benchmark packs', icon: BookOpen },
      { to: '/documents', label: 'RAG documents', icon: FileText },
    ],
  },
  {
    label: 'Analysis',
    items: [
      { to: '/experiments', label: 'Experiments', icon: FlaskConical },
      { to: '/compare', label: 'Compare', icon: GitCompare },
      { to: '/failures', label: 'Failures', icon: Activity },
      { to: '/recommendations', label: 'Recommendations', icon: Lightbulb },
      { to: '/reports', label: 'Reports', icon: BarChart3 },
      { to: '/calibration', label: 'Judge calibration', icon: Scale },
    ],
  },
]

export function Logo({ compact = false }) {
  return (
    <Link to="/" className="flex items-center gap-2.5 outline-none">
      <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-accent text-accent-ink shadow-card">
        <Beaker className="h-[1.05rem] w-[1.05rem]" />
      </span>
      {!compact ? (
        <span className="text-[1.05rem] font-semibold tracking-[-0.02em]">
          LLM<span className="text-accent">-</span>EvalHub
        </span>
      ) : null}
    </Link>
  )
}

export function ThemeToggle() {
  const { theme, toggle } = useTheme()
  return (
    <button
      onClick={toggle}
      className="relative flex h-9 w-9 items-center justify-center rounded-xl border border-line
                 bg-elevated text-muted transition-all duration-200 ease-spring
                 hover:border-accent/45 hover:text-accent"
      aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
      title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
    >
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={theme}
          initial={{ opacity: 0, rotate: -35, scale: 0.7 }}
          animate={{ opacity: 1, rotate: 0, scale: 1 }}
          exit={{ opacity: 0, rotate: 35, scale: 0.7 }}
          transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
        >
          {theme === 'dark' ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
        </motion.span>
      </AnimatePresence>
    </button>
  )
}

function NavItem({ to, label, icon: Icon, onNavigate }) {
  return (
    <NavLink
      to={to}
      onClick={onNavigate}
      className={({ isActive }) =>
        `group relative flex items-center gap-2.5 rounded-xl px-3 py-2 text-sm font-medium
         transition-colors duration-200 ${
           isActive ? 'text-accent' : 'text-muted hover:bg-overlay/70 hover:text-ink'
         }`
      }
    >
      {({ isActive }) => (
        <>
          {isActive ? (
            <motion.span
              layoutId="nav-active"
              className="absolute inset-0 rounded-xl border border-accent/25 bg-accent-soft/70"
              transition={{ type: 'spring', stiffness: 400, damping: 34 }}
            />
          ) : null}
          <Icon className="relative z-10 h-4 w-4 shrink-0" />
          <span className="relative z-10">{label}</span>
        </>
      )}
    </NavLink>
  )
}

function SidebarContent({ onNavigate, health }) {
  return (
    <>
      <div className="px-4 pb-5 pt-5">
        <Logo />
      </div>
      <nav className="flex-1 space-y-6 overflow-y-auto px-3 pb-4">
        {NAV_SECTIONS.map((section) => (
          <div key={section.label}>
            <p className="label mb-2 px-3">{section.label}</p>
            <div className="space-y-0.5">
              {section.items.map((item) => (
                <NavItem key={item.to} {...item} onNavigate={onNavigate} />
              ))}
            </div>
          </div>
        ))}
      </nav>
      <div className="border-t border-line px-3 py-3">
        <NavItem to="/settings" label="Settings & providers" icon={Settings} onNavigate={onNavigate} />
        {health ? (
          <div className="mt-3 rounded-xl border border-line bg-overlay/45 px-3 py-2.5">
            <div className="flex items-center justify-between gap-2">
              <span className="label">Providers</span>
              <Badge tone={health.providers_configured > 1 ? 'good' : 'fair'}>
                {health.providers_configured}/{health.providers_total}
              </Badge>
            </div>
            <p className="prose-note mt-1.5 text-[0.7rem] leading-snug">
              {health.providers_configured > 1
                ? 'Configured and ready to evaluate.'
                : 'Add a provider key in Settings to run real models.'}
            </p>
          </div>
        ) : null}
      </div>
    </>
  )
}

export default function AppLayout({ children }) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()
  const { data: health } = useApi(() => api.health(), [])

  useEffect(() => {
    setMobileOpen(false)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }, [location.pathname])

  return (
    <div className="relative z-[1] flex min-h-screen">
      {/* desktop sidebar */}
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-line bg-elevated/70 backdrop-blur lg:flex">
        <SidebarContent health={health} />
      </aside>

      {/* mobile drawer */}
      <AnimatePresence>
        {mobileOpen ? (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-40 bg-sand-950/45 backdrop-blur-sm lg:hidden"
              onClick={() => setMobileOpen(false)}
            />
            <motion.aside
              initial={{ x: -280 }}
              animate={{ x: 0 }}
              exit={{ x: -280 }}
              transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
              className="fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-line bg-elevated lg:hidden"
            >
              <button
                onClick={() => setMobileOpen(false)}
                className="absolute right-3 top-4 rounded-lg p-1.5 text-faint hover:bg-overlay hover:text-ink"
                aria-label="Close navigation"
              >
                <X className="h-4 w-4" />
              </button>
              <SidebarContent onNavigate={() => setMobileOpen(false)} health={health} />
            </motion.aside>
          </>
        ) : null}
      </AnimatePresence>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 border-b border-line bg-surface/80 backdrop-blur-md">
          <div className="flex h-14 items-center gap-3 px-4 sm:px-6">
            <button
              onClick={() => setMobileOpen(true)}
              className="rounded-xl border border-line bg-elevated p-2 text-muted transition-colors hover:text-ink lg:hidden"
              aria-label="Open navigation"
            >
              <Menu className="h-4 w-4" />
            </button>
            <div className="lg:hidden">
              <Logo compact />
            </div>
            <p className="ml-auto hidden text-xs text-faint sm:block">
              Evaluate → Compare → Diagnose → Recommend → Improve
            </p>
            <ThemeToggle />
          </div>
        </header>

        <main className="min-w-0 flex-1 px-4 py-7 sm:px-6 lg:px-8 lg:py-9">
          <div className="mx-auto w-full max-w-[1400px]">
            <AnimatePresence mode="wait">
              <motion.div
                key={location.pathname}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
              >
                {children}
              </motion.div>
            </AnimatePresence>
          </div>
        </main>

        <footer className="border-t border-line px-4 py-5 text-xs text-faint sm:px-6 lg:px-8">
          <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-3">
            <span>LLM-EvalHub — evaluation-first LLM &amp; RAG benchmarking.</span>
            <span>
              API keys stay server-side.{' '}
              <a
                href="/docs"
                target="_blank"
                rel="noreferrer"
                className="text-accent underline-offset-2 hover:underline"
              >
                OpenAPI docs
              </a>
            </span>
          </div>
        </footer>
      </div>
    </div>
  )
}
