/** Experiments — every reproducible configuration, with its run history. */
import { FlaskConical, GitBranch, Play, Plus, Search, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Reveal,
  ScoreBar,
  StatusBadge,
  useToast,
} from '../components/ui'
import { useApi, useDebounced } from '../hooks'
import { api } from '../lib/api'
import { NA, ms, num, pct, relativeTime, score, scoreTone } from '../lib/format'

export default function Experiments() {
  const toast = useToast()
  const [search, setSearch] = useState('')
  const debounced = useDebounced(search)
  const { data, loading, error, refetch } = useApi(
    () => api.experiments({ search: debounced || undefined, limit: 100 }),
    [debounced],
  )

  const experiments = data?.items || []

  const remove = async (experiment) => {
    try {
      await api.deleteExperiment(experiment.id)
      toast.success(`${experiment.name} deleted.`)
      refetch()
    } catch (err) {
      toast.error(err.message)
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Analysis"
        title="Experiments"
        description="An experiment freezes a dataset version, prompt, parameters, models, retrieval settings and metric selection. Runs point at an experiment, which is what makes a before/after comparison attributable to a specific change."
        actions={
          <Link to="/evaluations/new" className="btn-primary">
            <Plus className="h-4 w-4" />
            New experiment
          </Link>
        }
      />

      <div className="mb-5 relative max-w-md">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
        <input
          className="input pl-9"
          placeholder="Search experiments…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {loading ? (
        <LoadingState label="Loading experiments…" />
      ) : error ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : experiments.length === 0 ? (
        <EmptyState
          icon={FlaskConical}
          title={debounced ? 'No experiments match' : 'No experiments yet'}
          description="Configure and run an evaluation — the experiment record is created automatically."
          action={
            <Link to="/evaluations/new" className="btn-primary">
              <Play className="h-4 w-4" />
              Run an evaluation
            </Link>
          }
        />
      ) : (
        <div className="space-y-3">
          {experiments.map((experiment, index) => {
            const summary = experiment.latest_summary || {}
            return (
              <Reveal key={experiment.id} delay={Math.min(index * 0.04, 0.25)}>
                <Card hover className="p-5">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="mb-1.5 flex flex-wrap items-center gap-2">
                        <Link
                          to={`/experiments/${experiment.id}`}
                          className="text-[1.02rem] font-semibold text-ink hover:text-accent"
                        >
                          {experiment.name}
                        </Link>
                        {experiment.parent_experiment_id ? (
                          <Badge tone="accent" icon={GitBranch}>follow-up</Badge>
                        ) : null}
                        {experiment.rag_enabled ? <Badge tone="info">RAG</Badge> : null}
                        {experiment.prompt_label ? <Badge>{experiment.prompt_label}</Badge> : null}
                      </div>

                      <p className="prose-note text-xs">
                        {experiment.dataset_name || 'Unknown dataset'} ·{' '}
                        {experiment.models?.map((m) => m.model).join(', ') || 'no models'} ·{' '}
                        {experiment.run_count} run(s) · {relativeTime(experiment.created_at)}
                      </p>

                      {experiment.change_summary ? (
                        <p className="mt-2 rounded-lg bg-accent-soft/60 px-3 py-1.5 text-xs text-muted">
                          {experiment.change_summary}
                        </p>
                      ) : null}
                    </div>

                    <div className="flex items-center gap-4">
                      {experiment.latest_run_status ? (
                        <StatusBadge status={experiment.latest_run_status} />
                      ) : (
                        <Badge tone="neutral">never run</Badge>
                      )}
                      <button
                        onClick={() => remove(experiment)}
                        className="rounded-lg p-1.5 text-faint transition-colors hover:bg-[rgb(var(--bad))]/10 hover:text-[rgb(var(--bad))]"
                        aria-label="Delete experiment"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>

                  {experiment.latest_run_id ? (
                    <div className="mt-4 grid gap-4 border-t border-line pt-4 sm:grid-cols-4">
                      <div>
                        <p className="label mb-1">Quality</p>
                        <ScoreBar value={summary.avg_quality_score} tone={scoreTone(summary.avg_quality_score)} />
                      </div>
                      <div>
                        <p className="label mb-1">Failure rate</p>
                        <p className="mono text-sm">{pct(summary.failure_rate)}</p>
                      </div>
                      <div>
                        <p className="label mb-1">Latency</p>
                        <p className="mono text-sm">{ms(summary.avg_latency_ms)}</p>
                      </div>
                      <div className="flex items-end">
                        <Link
                          to={`/evaluations/${experiment.latest_run_id}`}
                          className="btn-ghost px-2.5 py-1.5 text-xs"
                        >
                          View latest run
                        </Link>
                      </div>
                    </div>
                  ) : null}
                </Card>
              </Reveal>
            )
          })}
        </div>
      )}
    </>
  )
}
