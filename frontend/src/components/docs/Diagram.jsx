import { Activity, ArrowRight, Database, GitCompare, Layers, Lightbulb, Play, RefreshCw, Stethoscope } from 'lucide-react'

export function Diagram({ name = 'evaluation-loop', caption, className = '' }) {
  if (name === 'evaluation-loop') {
    return (
      <div className={`my-8 space-y-3 ${className}`}>
        <div className="rounded-2xl border border-line bg-elevated p-6 shadow-card">
          <div className="mb-4 flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-accent">Interactive Lifecycle Diagram</span>
            <span className="text-xs text-faint">Continuous Improvement Cycle</span>
          </div>

          {/* Flow cards with connectors */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {[
              { num: '01', title: 'Evaluate', icon: Play, desc: 'Identical inputs across models' },
              { num: '02', title: 'Compare', icon: GitCompare, desc: 'Side-by-side metric deltas' },
              { num: '03', title: 'Diagnose', icon: Stethoscope, desc: 'Evidence-based root cause' },
              { num: '04', title: 'Recommend', icon: Lightbulb, desc: 'Transparent profile scoring' },
              { num: '05', title: 'Improve', icon: RefreshCw, desc: 'Targeted single-field fix' },
              { num: '06', title: 'Re-evaluate', icon: Activity, desc: 'Verify before vs after delta' },
            ].map((step, idx) => (
              <div
                key={step.title}
                className="relative flex flex-col justify-between rounded-xl border border-line bg-surface p-3.5 text-center transition-all hover:border-accent/50"
              >
                <div className="mb-2 flex items-center justify-between text-xs">
                  <span className="mono font-semibold text-accent">{step.num}</span>
                  <step.icon className="h-4 w-4 text-muted" />
                </div>
                <h5 className="text-sm font-semibold text-ink">{step.title}</h5>
                <p className="mt-1 text-[0.72rem] leading-tight text-faint">{step.desc}</p>
                {idx < 5 ? (
                  <div className="hidden lg:block absolute -right-2 top-1/2 -translate-y-1/2 z-10 translate-x-1/2">
                    <ArrowRight className="h-3 w-3 text-accent" />
                  </div>
                ) : null}
              </div>
            ))}
          </div>

          {/* SVG Return Arrow */}
          <div className="mt-4 flex items-center justify-center gap-2 rounded-xl border border-line/60 bg-overlay/50 py-2.5 px-4 text-xs text-muted">
            <RefreshCw className="h-3.5 w-3.5 text-accent animate-spin-slow" />
            <span className="font-medium text-ink">Cycle feeds back:</span>
            <span>Step 06 (Re-evaluate) verifies the outcome and feeds into the next baseline iteration.</span>
          </div>
        </div>
        {caption && <p className="text-center text-xs text-faint">{caption}</p>}
      </div>
    )
  }

  if (name === 'architecture') {
    return (
      <div className={`my-8 space-y-3 ${className}`}>
        <div className="rounded-2xl border border-line bg-elevated p-6 shadow-card space-y-4">
          <div className="flex items-center justify-between border-b border-line pb-3">
            <span className="text-xs font-semibold uppercase tracking-wider text-accent">System Architecture</span>
            <span className="text-xs text-faint">Layered Component Separation</span>
          </div>

          <div className="space-y-3">
            {/* Layer 1: Presentation */}
            <div className="rounded-xl border border-line bg-surface p-4">
              <div className="flex items-center justify-between text-xs font-semibold text-ink mb-1.5">
                <span className="flex items-center gap-2">
                  <Layers className="h-4 w-4 text-accent" />
                  Presentation Layer (Frontend)
                </span>
                <span className="text-faint">Port 5173 / Client Browser</span>
              </div>
              <p className="text-xs text-muted">React 19, Vite, Tailwind CSS (theme tokens only), Source Serif 4 typography, Recharts, Framer Motion.</p>
            </div>

            {/* Layer 2: API & Security */}
            <div className="rounded-xl border border-line bg-surface p-4">
              <div className="flex items-center justify-between text-xs font-semibold text-ink mb-1.5">
                <span className="flex items-center gap-2">
                  <Layers className="h-4 w-4 text-accent" />
                  API &amp; Security Layer
                </span>
                <span className="text-faint">Port 8000 / FastAPI</span>
              </div>
              <p className="text-xs text-muted">FastAPI router (/api), Security Headers, Request ID Tracing, Strict CORS, Secret Redaction, Owner-Only Audit Logs.</p>
            </div>

            {/* Layer 3: Orchestration & Workflows */}
            <div className="rounded-xl border border-line bg-surface p-4">
              <div className="flex items-center justify-between text-xs font-semibold text-ink mb-1.5">
                <span className="flex items-center gap-2">
                  <Layers className="h-4 w-4 text-accent" />
                  Orchestration &amp; Background Execution
                </span>
                <span className="text-faint">JobService (asyncio / arq + Redis)</span>
              </div>
              <p className="text-xs text-muted">Durable job state machine (queued, running, completed, failed, cancelled, interrupted), LangGraph stateful execution.</p>
            </div>

            {/* Layer 4: Evaluation, Providers, RAG */}
            <div className="rounded-xl border border-line bg-surface p-4">
              <div className="flex items-center justify-between text-xs font-semibold text-ink mb-1.5">
                <span className="flex items-center gap-2">
                  <Layers className="h-4 w-4 text-accent" />
                  Evaluation, Providers &amp; RAG Engine
                </span>
                <span className="text-faint">Server-side execution</span>
              </div>
              <p className="text-xs text-muted">Multi-provider adapters (Gemini, Groq, HF, NVIDIA, OpenRouter, Mock), Deterministic &amp; LLM Judges, Lexical Hashing &amp; Vector Index.</p>
            </div>

            {/* Layer 5: Persistence */}
            <div className="rounded-xl border border-line bg-surface p-4">
              <div className="flex items-center justify-between text-xs font-semibold text-ink mb-1.5">
                <span className="flex items-center gap-2">
                  <Database className="h-4 w-4 text-accent" />
                  Persistence Layer
                </span>
                <span className="text-faint">SQLite (local) or PostgreSQL (prod)</span>
              </div>
              <p className="text-xs text-muted">SQLAlchemy 2.0 ORM, 29 Alembic-migrated tables with tenant isolation via workspace_id.</p>
            </div>
          </div>
        </div>
        {caption && <p className="text-center text-xs text-faint">{caption}</p>}
      </div>
    )
  }

  if (name === 'workflow') {
    return (
      <div className={`my-8 space-y-3 ${className}`}>
        <div className="rounded-2xl border border-line bg-elevated p-6 shadow-card">
          <div className="mb-4 flex items-center justify-between border-b border-line pb-3">
            <span className="text-xs font-semibold uppercase tracking-wider text-accent">LangGraph Work-Unit Workflow</span>
            <span className="text-xs text-faint">State machine executed per test-case &times; model</span>
          </div>

          <div className="flex flex-col md:flex-row items-stretch justify-between gap-2 text-xs">
            {[
              { step: 'prepare', desc: 'Load test case & prompt template' },
              { step: 'retrieve?', desc: 'RAG retrieval if document attached' },
              { step: 'generate', desc: 'Call provider model adapter' },
              { step: 'evaluate', desc: 'Execute configured metrics' },
              { step: 'detect_failure', desc: 'Evaluate cascade rules' },
              { step: 'persist', desc: 'Save EvaluationResult to DB' },
            ].map((node, i) => (
              <div key={node.step} className="flex-1 flex flex-col items-center justify-center rounded-xl border border-line bg-surface p-3 text-center">
                <span className="mono font-semibold text-accent mb-1">{node.step}</span>
                <span className="text-faint text-[0.7rem]">{node.desc}</span>
              </div>
            ))}
          </div>
        </div>
        {caption && <p className="text-center text-xs text-faint">{caption}</p>}
      </div>
    )
  }

  return null
}
