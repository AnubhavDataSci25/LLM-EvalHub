/** Marketing / orientation page — explains the product loop before the app. */
import { motion } from 'framer-motion'
import {
  ArrowRight,
  Activity,
  Beaker,
  BookOpen,
  GitCompare,
  Lightbulb,
  Play,
  RefreshCw,
  ShieldCheck,
  Stethoscope,
} from 'lucide-react'
import { Link } from 'react-router-dom'

import { ThemeToggle, Logo } from '../components/layout/AppLayout'
import { Badge, Button, Card, Reveal } from '../components/ui'
import { useApi } from '../hooks'
import { api } from '../lib/api'
import { num } from '../lib/format'

const LOOP = [
  {
    icon: Play,
    title: 'Evaluate',
    body: 'Run one dataset against several providers and models at once. Identical inputs, so differences are attributable.',
  },
  {
    icon: GitCompare,
    title: 'Compare',
    body: 'Side-by-side metrics, latency and failure rates — with the sample size behind every number.',
  },
  {
    icon: Stethoscope,
    title: 'Diagnose',
    body: 'Every failure is classified and explained from stored evidence: retrieval gap, hallucination, timeout, empty output.',
  },
  {
    icon: Lightbulb,
    title: 'Recommend',
    body: 'A weighted, constrained ranking with a visible score breakdown — scoped to your data, never a universal claim.',
  },
  {
    icon: RefreshCw,
    title: 'Improve',
    body: 'Accept a suggested change, and a follow-up experiment is created that differs in exactly that one field.',
  },
  {
    icon: Activity,
    title: 'Re-evaluate',
    body: 'Re-run and get a before/after verdict that says whether the change actually helped.',
  },
]

const PRINCIPLES = [
  {
    title: 'No invented numbers',
    body: 'A metric that cannot be computed is reported as unavailable, with the reason. It is never silently scored as zero, because a zero and an unknown mean very different things when you are choosing a model.',
  },
  {
    title: 'Deterministic and judged metrics are labelled',
    body: 'Lexical evaluators are reproducible; LLM judges are not. Every score carries its kind and, where relevant, the judge model that produced it, so you know how much to trust it.',
  },
  {
    title: 'Keys never reach the browser',
    body: 'All provider calls are proxied through the FastAPI backend. The frontend only ever sees whether a provider is configured — never the credential.',
  },
  {
    title: 'Failures are evidence, not vibes',
    body: 'Classification runs an ordered cascade over measured signals: infrastructure first, then retrieval, then grounding, then answer quality. Low retrieval recall is reported as a retrieval problem, not a hallucination.',
  },
]

export default function Landing() {
  const { data: health } = useApi(() => api.health(), [])
  const { data: dashboard } = useApi(() => api.dashboard(), [])
  const kpis = dashboard?.kpis

  return (
    <div className="relative z-[1] min-h-screen">
      <header className="sticky top-0 z-30 border-b border-line bg-surface/85 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-4 px-4 sm:px-6">
          <Logo />
          <nav className="ml-auto flex items-center gap-2">
            <a
              href="/docs"
              target="_blank"
              rel="noreferrer"
              className="btn-ghost hidden sm:inline-flex"
            >
              API docs
            </a>
            <Link to="/dashboard" className="btn-primary">
              Open the app
              <ArrowRight className="h-4 w-4" />
            </Link>
            <ThemeToggle />
          </nav>
        </div>
      </header>

      {/* ---------------------------------------------------------------- hero */}
      <section className="mx-auto max-w-6xl px-4 pb-16 pt-16 sm:px-6 sm:pt-24">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
          className="max-w-3xl"
        >
          <Badge tone="accent" icon={Beaker} className="mb-5">
            Evaluation-first GenAI platform
          </Badge>
          <h1 className="text-[2.4rem] font-semibold leading-[1.1] tracking-[-0.035em] sm:text-[3.4rem]">
            Stop guessing which model is better.
            <span className="block text-accent">Measure it, then prove the fix worked.</span>
          </h1>
          <p className="prose-note mt-6 max-w-2xl text-[1.02rem] leading-relaxed">
            LLM-EvalHub runs the same test cases against Gemini, Groq, Hugging Face, NVIDIA NIM and
            OpenRouter, scores the answers, explains why the failures happened, and creates the
            follow-up experiment that tests your fix. Every number traces back to a stored result.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link to="/evaluations/new" className="btn-primary">
              <Play className="h-4 w-4" />
              Run an evaluation
            </Link>
            <Link to="/benchmarks" className="btn-secondary">
              <BookOpen className="h-4 w-4" />
              Start from a benchmark pack
            </Link>
          </div>

          {health ? (
            <p className="mt-6 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-faint">
              <span className="inline-flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-[rgb(var(--ok))]" />
                API healthy · {health.database}
              </span>
              <span>
                {health.providers_configured} of {health.providers_total} providers configured
              </span>
              {kpis?.evaluation_runs ? (
                <span>
                  {num(kpis.evaluation_runs)} run(s) · {num(kpis.results)} scored result(s)
                </span>
              ) : null}
            </p>
          ) : null}
        </motion.div>
      </section>

      {/* ---------------------------------------------------------------- loop */}
      <section className="border-y border-line bg-overlay/30 py-16">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <Reveal>
            <p className="label mb-2">The product loop</p>
            <h2 className="max-w-2xl text-[1.7rem] font-semibold tracking-[-0.025em] sm:text-[2rem]">
              Six steps, and the sixth feeds the first
            </h2>
            <p className="prose-note mt-3 max-w-2xl">
              Most evaluation tools stop at a leaderboard. The useful part is what comes after: why
              did it fail, what should change, and did that change help?
            </p>
          </Reveal>

          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {LOOP.map((step, index) => (
              <Reveal key={step.title} delay={index * 0.06}>
                <Card hover className="h-full p-5">
                  <div className="mb-3.5 flex items-center gap-3">
                    <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-line bg-surface text-accent">
                      <step.icon className="h-[1.05rem] w-[1.05rem]" />
                    </span>
                    <span className="mono text-xs text-faint">0{index + 1}</span>
                  </div>
                  <h3 className="text-[1.05rem] font-semibold">{step.title}</h3>
                  <p className="prose-note mt-2 text-[0.87rem] leading-relaxed">{step.body}</p>
                </Card>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------ principles */}
      <section className="py-16">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <div className="grid gap-10 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
            <Reveal>
              <Badge tone="accent" icon={ShieldCheck} className="mb-4">
                Evaluation integrity
              </Badge>
              <h2 className="text-[1.7rem] font-semibold tracking-[-0.025em] sm:text-[2rem]">
                An evaluation tool is only worth the honesty of its numbers
              </h2>
              <p className="prose-note mt-4">
                These four rules are enforced in the code, not just documented. They are what make
                the platform usable for a decision you would defend in a design review.
              </p>
            </Reveal>

            <div className="space-y-3.5">
              {PRINCIPLES.map((principle, index) => (
                <Reveal key={principle.title} delay={index * 0.06}>
                  <Card className="p-5">
                    <h3 className="text-[0.98rem] font-semibold">{principle.title}</h3>
                    <p className="prose-note mt-2 text-[0.87rem] leading-relaxed">
                      {principle.body}
                    </p>
                  </Card>
                </Reveal>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------------- cta */}
      <section className="border-t border-line bg-overlay/30 py-16">
        <div className="mx-auto max-w-3xl px-4 text-center sm:px-6">
          <Reveal>
            <h2 className="text-[1.7rem] font-semibold tracking-[-0.025em] sm:text-[2rem]">
              Six benchmark packs are already loaded
            </h2>
            <p className="prose-note mx-auto mt-3.5 max-w-xl">
              RAG QA, customer support, document extraction, citation grounding, structured
              extraction and summarization — each with a dataset, recommended metrics and baseline
              settings. Install one and you have a real evaluation in two clicks.
            </p>
            <div className="mt-7 flex flex-wrap justify-center gap-3">
              <Link to="/benchmarks" className="btn-primary">
                Browse benchmark packs
                <ArrowRight className="h-4 w-4" />
              </Link>
              <Link to="/dashboard" className="btn-secondary">
                Go to the dashboard
              </Link>
            </div>
          </Reveal>
        </div>
      </section>

      <footer className="border-t border-line px-4 py-8 text-center text-xs text-faint sm:px-6">
        LLM-EvalHub · Built with FastAPI, LangChain, LangGraph, React and Recharts.
      </footer>
    </div>
  )
}
